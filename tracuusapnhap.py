import streamlit as st
import pandas as pd
import re
import io
import gspread
from google.oauth2.service_account import Credentials
import time

# ==========================================
# CẤU HÌNH GIAO DIỆN & MÀU SẮC
# ==========================================
st.set_page_config(page_title="TRA CỨU SÁP NHẬP", layout="wide")

st.markdown("""
<style>
    /* Nền sáng dễ làm việc Excel */
    .stApp { background-color: #f8f9fa; }
    
    /* Chữ Gradient cho Tiêu đề */
    h1, h2, h3 {
        background: -webkit-linear-gradient(45deg, #FF1493, #8A2BE2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: bold;
    }
    
    /* Nút bấm chủ đạo Hồng - Tím */
    .stButton>button {
        background: linear-gradient(135deg, #FF1493 0%, #8A2BE2 100%);
        color: white !important;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover { transform: scale(1.02); box-shadow: 0 4px 10px rgba(138, 43, 226, 0.4); }
    
    /* Làm nổi bật form input */
    .stTextInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; font-size: 3em;'>TRA CỨU SÁP NHẬP 2024-2030</h1>", unsafe_allow_html=True)

# ==========================================
# KẾT NỐI API & TẢI DỮ LIỆU
# ==========================================
SHEET_ID = "15vjVT7KFUVj_7aawYD-leKSdzAWGNdDzZAS-GmrOtl4"

@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

@st.cache_data(ttl=0)
def load_data():
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID)
    df_map = pd.DataFrame(sheet.worksheet("Mapping").get_all_records())
    df_dict = pd.DataFrame(sheet.worksheet("Dict").get_all_records())
    
    # Ép kiểu string để tránh lỗi số nguyên
    for col in df_map.columns:
        df_map[col] = df_map[col].astype(str).str.strip()
        
    return df_map, df_dict

if 'last_update' not in st.session_state:
    st.session_state.last_update = time.strftime("%H:%M:%S %d/%m/%Y")
if 'pending_words' not in st.session_state:
    st.session_state.pending_words = set()

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🔄 Cập nhật dữ liệu mới nhất từ Master", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_update = time.strftime("%H:%M:%S %d/%m/%Y")
        st.rerun()
st.markdown(f"<p style='text-align: center; color: gray;'><i>Cập nhật lần cuối: {st.session_state.last_update}</i></p>", unsafe_allow_html=True)

df_map, df_dict = load_data()

# ==========================================
# BỘ XỬ LÝ CHUỖI & TỪ ĐIỂN
# ==========================================
# Nạp từ điển người dùng
user_dict = {}
if not df_dict.empty:
    for _, row in df_dict.iterrows():
        chuan = str(row.get('Địa danh', '')).strip().lower()
        tu_dien = str(row.get('Từ điển', '')).split(',')
        for td in tu_dien:
            if td.strip():
                user_dict[td.strip().lower()] = chuan

def pre_clean_text(text):
    if not isinstance(text, str): return ""
    text = text.lower()
    # Thay thế từ điển user nạp (VD: qbinh thanh -> bình thạnh)
    for typo, correct in user_dict.items():
        if typo in text:
            text = text.replace(typo, correct)
    
    # Tách số dính chữ (P27 -> p 27)
    text = re.sub(r'\b(q|p|f|d)(\d+)\b', r'\1 \2', text)
    # Bỏ dấu câu để dễ regex
    text = re.sub(r'[,.\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def remove_administrative_prefixes(text):
    stop_words = r'\b(tỉnh|thành phố|tp|quận|q|huyện|h|thị xã|tx|phường|p|xã|x|thị trấn|tt)\b'
    return re.sub(stop_words, '', text).strip()

def detect_address_status(ward_val, dist_val, prov_val, df_map):
    """ Dành cho Option 1 & 2 (Tách cột rõ ràng) - Đảm bảo chính xác 100% """
    w = remove_administrative_prefixes(pre_clean_text(str(ward_val)))
    d = remove_administrative_prefixes(pre_clean_text(str(dist_val)))
    p = remove_administrative_prefixes(pre_clean_text(str(prov_val)))
    
    # 1. Soi xem nó có nằm bên cột CŨ không?
    for _, row in df_map.iterrows():
        r_w_cu = remove_administrative_prefixes(pre_clean_text(row['Phường/Xã cũ']))
        r_d_cu = remove_administrative_prefixes(pre_clean_text(row['Quận/Huyện cũ']))
        # Match linh hoạt Phường (bắt buộc) và Huyện (nếu có)
        if r_w_cu == w:
            if not d or r_d_cu == d or d in r_d_cu:
                return f"{row['Phường/Xã mới']}, {row['Tỉnh/Thành phố mới']}", "Đã chuyển đổi (Từ địa chỉ Cũ)"
                
    # 2. Soi xem nó có phải ĐÃ LÀ ĐỊA CHỈ MỚI không?
    for _, row in df_map.iterrows():
        r_w_moi = remove_administrative_prefixes(pre_clean_text(row['Phường/Xã mới']))
        if r_w_moi == w:
            return ward_val, "Đã là địa chỉ Mới (Giữ nguyên)"
            
    return "", "⚠️ Cần xác nhận"

def smart_scan_free_text(raw_string, df_map):
    """ Dành cho Option 3 (File 1 cột) - Dò tìm substring (chữ con) bên trong câu dài """
    cleaned = pre_clean_text(raw_string)
    
    # 1. Quét tìm xem trong câu có chứa cụm [Phường Cũ + Huyện Cũ] không?
    for _, row in df_map.iterrows():
        w_cu = remove_administrative_prefixes(pre_clean_text(row['Phường/Xã cũ']))
        d_cu = remove_administrative_prefixes(pre_clean_text(row['Quận/Huyện cũ']))
        
        # Nếu trong câu có nhắc tới chữ Phường cũ
        if re.search(r'\b' + re.escape(w_cu) + r'\b', cleaned):
            # Càng chính xác hơn nếu có nhắc cả chữ Huyện, hoặc khuyết Huyện
            if not d_cu or d_cu == 'chưa rõ' or re.search(r'\b' + re.escape(d_cu) + r'\b', cleaned):
                # Phát hiện địa chỉ cũ -> Replace tên phường bằng tên mới
                # Regex phức tạp để replace đúng tên riêng mà ko làm hỏng câu
                new_str = re.sub(r'(?i)\b' + re.escape(row['Phường/Xã cũ']) + r'\b', row['Phường/Xã mới'], raw_string)
                return new_str, "Đã chuyển đổi"
                
    # 2. Quét xem trong câu đã có sẵn Phường Mới chưa (Người ta đã update rồi)
    for _, row in df_map.iterrows():
        w_moi = remove_administrative_prefixes(pre_clean_text(row['Phường/Xã mới']))
        if re.search(r'\b' + re.escape(w_moi) + r'\b', cleaned):
            return raw_string, "Đã là địa chỉ Mới"

    return raw_string, "⚠️ Cần xác nhận"

# ==========================================
# CẤU TRÚC GIAO DIỆN (3 TAB)
# ==========================================
tab1, tab2, tab3 = st.tabs(["🔍 TRA CỨU DANH MỤC", "📁 XỬ LÝ CHUYỂN ĐỔI", "🧠 HUẤN LUYỆN TỪ ĐIỂN"])

# ----------------- TAB 1: TRA CỨU -----------------
with tab1:
    st.markdown("### Tra cứu nhanh Cấp Hành chính")
    chieu_tra_cuu = st.radio("Chọn chiều tra cứu:", ["Từ Cũ sang Mới", "Từ Mới truy ngược Cũ"], horizontal=True)
    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
    
    if not df_map.empty:
        if chieu_tra_cuu == "Từ Cũ sang Mới":
            c1, c2, c3 = st.columns(3)
            with c1:
                tinh_opts = ["-- Tất cả --"] + sorted(df_map['Tỉnh/Thành phố cũ'].unique().tolist())
                tinh = st.selectbox("1. Tỉnh/Thành phố (Cũ):", options=tinh_opts)
            with c2:
                huyen_opts = ["-- Tất cả --"] + sorted(df_map[df_map['Tỉnh/Thành phố cũ'] == tinh]['Quận/Huyện cũ'].unique().tolist()) if tinh != "-- Tất cả --" else ["-- Tất cả --"]
                huyen = st.selectbox("2. Quận/Huyện (Cũ):", options=huyen_opts)
            with c3:
                xa_opts = ["-- Tất cả --"] + sorted(df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen)]['Phường/Xã cũ'].unique().tolist()) if huyen != "-- Tất cả --" else ["-- Tất cả --"]
                xa = st.selectbox("3. Phường/Xã (Cũ):", options=xa_opts)
                
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔍 Bắt đầu Tra cứu", use_container_width=True):
                if tinh == "-- Tất cả --": st.warning("Vui lòng chọn Tỉnh/Thành phố!")
                elif huyen == "-- Tất cả --" and xa == "-- Tất cả --":
                    st.info(f"📍 **Tỉnh/Thành phố tương đương:** {df_map[df_map['Tỉnh/Thành phố cũ'] == tinh]['Tỉnh/Thành phố mới'].iloc[0]}")
                elif xa == "-- Tất cả --":
                    kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen)]
                    st.success(f"📍 Các Phường/Xã mới thuộc {huyen}:")
                    st.dataframe(kq[['Phường/Xã cũ', 'Tỉnh/Thành phố mới', 'Phường/Xã mới']], use_container_width=True, hide_index=True)
                else:
                    kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen) & (df_map['Phường/Xã cũ'] == xa)].iloc[0]
                    st.info(f"📍 **Tỉnh/Thành mới:** {kq['Tỉnh/Thành phố mới']} \n\n📍 **Phường/Xã mới:** {kq['Phường/Xã mới']}")

        else: # Chiều Mới -> Cũ
            c1, c2 = st.columns(2)
            with c1:
                tinh_moi = st.selectbox("1. Tỉnh/Thành phố (Mới):", options=["-- Tất cả --"] + sorted(df_map['Tỉnh/Thành phố mới'].unique().tolist()))
            with c2:
                xa_moi = st.selectbox("2. Phường/Xã (Mới):", options=["-- Tất cả --"] + sorted(df_map[df_map['Tỉnh/Thành phố mới'] == tinh_moi]['Phường/Xã mới'].unique().tolist()) if tinh_moi != "-- Tất cả --" else ["-- Tất cả --"])
                
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔍 Truy vết Nguồn gốc", use_container_width=True):
                if tinh_moi == "-- Tất cả --": st.warning("Vui lòng chọn Tỉnh/Thành phố!")
                elif xa_moi == "-- Tất cả --":
                    st.info(f"📍 **Nguồn gốc:** {', '.join(df_map[df_map['Tỉnh/Thành phố mới'] == tinh_moi]['Tỉnh/Thành phố cũ'].unique())}")
                else:
                    kq = df_map[(df_map['Tỉnh/Thành phố mới'] == tinh_moi) & (df_map['Phường/Xã mới'] == xa_moi)]
                    st.success(f"📍 Các đơn vị cũ cấu thành:")
                    st.dataframe(kq[['Tỉnh/Thành phố cũ', 'Quận/Huyện cũ', 'Phường/Xã cũ']], use_container_width=True, hide_index=True)

# ----------------- TAB 2: XỬ LÝ FILE -----------------
with tab2:
    st.markdown("### Chọn phương thức xử lý địa chỉ")
    option = st.radio("", [
        "1️⃣ Chuyển đổi Đơn lẻ (Điền Form)", 
        "2️⃣ File Mẫu Chuẩn (Tách sẵn cột Phường, Quận)", 
        "3️⃣ File Tự Do (Địa chỉ gom chung 1 cột)"
    ], horizontal=True)
    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

    if option.startswith("1️⃣"):
        c_p, c_q, c_t = st.columns(3)
        with c_p: p_input = st.text_input("Nhập Phường/Xã:")
        with c_q: q_input = st.text_input("Nhập Quận/Huyện:")
        with c_t: t_input = st.text_input("Nhập Tỉnh/Thành:")
        
        if st.button("Chuyển đổi ngay", use_container_width=True):
            if not p_input: st.warning("Vui lòng nhập ít nhất Phường/Xã")
            else:
                new_addr, status = detect_address_status(p_input, q_input, t_input, df_map)
                if "⚠️" in status: st.error("Không nhận diện được. Vui lòng check chính tả hoặc thêm vào Từ điển.")
                else: st.success(f"**Kết quả:** {new_addr} - {status}")

    elif option.startswith("2️⃣"):
        st.info("💡 Cách này có độ chính xác 100% vì dữ liệu đã được tách lớp rõ ràng.")
        upl_2 = st.file_uploader("Upload Excel có chia cột rõ ràng", type=['xlsx'], key="file2")
        if upl_2:
            df_in = pd.read_excel(upl_2)
            c1, c2, c3 = st.columns(3)
            with c1: col_w = st.selectbox("Cột Phường/Xã:", df_in.columns)
            with c2: col_d = st.selectbox("Cột Quận/Huyện:", df_in.columns)
            with c3: col_p = st.selectbox("Cột Tỉnh/Thành:", df_in.columns)
            
            if st.button("🚀 Bắt đầu Quét File", use_container_width=True):
                res_addr, res_status = [], []
                for _, row in df_in.iterrows():
                    new_a, stat = detect_address_status(row[col_w], row[col_d], row[col_p], df_map)
                    res_addr.append(new_a)
                    res_status.append(stat)
                df_in['[Hệ Thống] Kết quả'] = res_addr
                df_in['[Hệ Thống] Trạng thái'] = res_status
                
                st.dataframe(df_in)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_in.to_excel(writer, index=False)
                st.download_button("📥 Tải File Đã Xử Lý", data=output.getvalue(), file_name="DiaChi_Chuan.xlsx")

    elif option.startswith("3️⃣"):
        st.warning("⚠️ Cách này dùng AI quét chuỗi nên có thể gặp rủi ro nếu địa chỉ chứa quá nhiều ký tự nhiễu.")
        upl_3 = st.file_uploader("Upload Excel chứa địa chỉ trộn chung", type=['xlsx'], key="file3")
        if upl_3:
            df_in3 = pd.read_excel(upl_3)
            col_addr = st.selectbox("Chọn Cột Địa Chỉ Đầy Đủ:", df_in3.columns)
            
            if st.button("🚀 Bắt đầu Quét Chuỗi", use_container_width=True):
                res_addr, res_status = [], []
                new_pendings = set()
                
                with st.spinner("Đang cho AI Săn lùng từ khóa trong chuỗi..."):
                    for _, row in df_in3.iterrows():
                        raw_str = str(row[col_addr])
                        new_str, stat = smart_scan_free_text(raw_str, df_map)
                        res_addr.append(new_str)
                        res_status.append(stat)
                        if "⚠️" in stat:
                            new_pendings.add(raw_str)
                            
                df_in3['[Hệ Thống] Kết quả'] = res_addr
                df_in3['[Hệ Thống] Trạng thái'] = res_status
                
                st.session_state.pending_words.update(new_pendings)
                st.dataframe(df_in3)
                
                if new_pendings: st.error(f"Phát hiện {len(new_pendings)} địa chỉ không nhận diện được. Hãy qua Tab 3 để dạy hệ thống!")
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_in3.to_excel(writer, index=False)
                st.download_button("📥 Tải File Đã Xử Lý", data=output.getvalue(), file_name="DiaChi_Scan.xlsx")

# ----------------- TAB 3: HUẤN LUYỆN -----------------
with tab3:
    st.markdown("### 🧠 Dạy hệ thống nhận diện TỪ GÕ SAI (Từ điển)")
    st.write("Nếu Tab 2 bó tay với từ nào, nó sẽ thảy qua đây. Bạn map từ gõ sai với từ chuẩn 1 lần, hệ thống tự lưu vào Google Sheet và vĩnh viễn học được.")
    
    if not st.session_state.pending_words:
        st.success("Tuyệt vời! Hiện không có từ lạ nào bị kẹt.")
    else:
        all_wards = list(set(df_map['Phường/Xã cũ'].unique().tolist() + df_map['Phường/Xã mới'].unique().tolist() + df_map['Quận/Huyện cũ'].unique().tolist()))
        
        for word in list(st.session_state.pending_words)[:5]: # Hiển thị 5 từ 1 lúc cho đỡ lag
            c_a, c_b, c_c = st.columns([2, 3, 1])
            with c_a: st.text_input("Chuỗi lỗi (Pending):", value=word, disabled=True)
            with c_b: chosen = st.selectbox("Gán vào Danh mục chuẩn:", options=["-- Bỏ qua --"] + sorted(all_wards), key=f"sel_{word}")
            with c_c:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Lưu lên GG Sheet", key=f"btn_{word}"):
                    if chosen != "-- Bỏ qua --":
                        client = get_gspread_client()
                        sheet = client.open_by_key(SHEET_ID).worksheet("Dict")
                        records = sheet.get_all_records()
                        found = False
                        # Format từ gõ sai để lưu (Ví dụ người ta gõ "qbinh thanh", m map với "Bình Thạnh")
                        typo_extract = st.text_input(f"Trích xuất riêng cái chữ bị gõ sai trong câu trên (VD: qbinh thanh):", key=f"txt_{word}")
                        
                        if typo_extract:
                            for i, r in enumerate(records):
                                if str(r.get('Địa danh', '')).strip() == chosen:
                                    cur = sheet.acell(f'B{i+2}').value or ""
                                    sheet.update_acell(f'B{i+2}', f"{cur}, {typo_extract}" if cur else typo_extract)
                                    found = True; break
                            if not found: sheet.append_row([chosen, typo_extract])
                            
                            st.session_state.pending_words.remove(word)
                            st.cache_data.clear()
                            st.success("Đã ghi thành công!")
                            time.sleep(1)
                            st.rerun()
