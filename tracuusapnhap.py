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
    /* 1. Trả nền về màu sáng mặc định của Streamlit */
    .stApp {
        background-color: #f8f9fa; /* Trắng xám nhẹ cho dịu mắt */
    }
    
    /* 2. Tiêu đề H1, H2, H3 áp dụng hiệu ứng chữ Gradient Hồng - Tím */
    h1, h2, h3 {
        background: -webkit-linear-gradient(45deg, #FF1493, #8A2BE2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: bold;
    }

    /* 3. Nút bấm mang màu cờ sắc áo */
    .stButton>button {
        background: linear-gradient(135deg, #FF1493 0%, #8A2BE2 100%);
        color: white !important;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: scale(1.02); /* Phóng to nhẹ khi rê chuột */
        box-shadow: 0 4px 10px rgba(138, 43, 226, 0.4);
        color: white !important;
    }
    
    /* 4. Viền và nền nhẹ cho các hộp thông báo Info / Success */
    div[data-testid="stInfo"] {
        border-left-color: #8A2BE2;
        background-color: rgba(138, 43, 226, 0.05);
    }
    div[data-testid="stSuccess"] {
        border-left-color: #FF1493;
        background-color: rgba(255, 20, 147, 0.05);
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; font-size: 3em;'>TRA CỨU SÁP NHẬP</h1>", unsafe_allow_html=True)

# ==========================================
# KẾT NỐI API & TẢI DỮ LIỆU
# ==========================================
SHEET_ID = "15vjVT7KFUVj_7aawYD-leKSdzAWGNdDzZAS-GmrOtl4"

@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    return gspread.authorize(credentials)

@st.cache_data(ttl=0)
def load_data():
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID)
    
    # Load Mapping
    ws_map = sheet.worksheet("Mapping")
    df_map = pd.DataFrame(ws_map.get_all_records())
    
    # Load Dict
    ws_dict = sheet.worksheet("Dict")
    df_dict = pd.DataFrame(ws_dict.get_all_records())
    
    return df_map, df_dict

if 'last_update' not in st.session_state:
    st.session_state.last_update = time.strftime("%H:%M:%S %d/%m/%Y")
if 'pending_words' not in st.session_state:
    st.session_state.pending_words = set()

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🔄 Cập nhật dữ liệu mới nhất", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_update = time.strftime("%H:%M:%S %d/%m/%Y")
        st.rerun()
st.markdown(f"<p style='text-align: center;'><i>Cập nhật lần cuối: {st.session_state.last_update}</i></p>", unsafe_allow_html=True)

df_map, df_dict = load_data()

# ==========================================
# BỘ CÔNG CỤ RULE-BASED TIỀN XỬ LÝ
# ==========================================
def clean_address_string(text):
    if not isinstance(text, str): return ""
    text = text.lower()
    text = re.sub(r'[,.\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\b(q|p|f|d)(\d+)\b', r'\1 \2', text)
    stop_words = r'\b(tỉnh|thành phố|tp|quận|q|huyện|h|thị xã|tx|phường|p|xã|x|thị trấn|tt)\b'
    text = re.sub(stop_words, '', text)
    return re.sub(r'\s+', ' ', text).strip()

def build_abbreviation_dict(df):
    abbr_dict = {}
    if not df.empty:
        tinh_cu = df['Tỉnh/Thành phố cũ'].dropna().unique()
        for tinh in tinh_cu:
            tinh_clean = clean_address_string(tinh)
            abbr = "".join([w[0] for w in tinh_clean.split() if w])
            if abbr:
                if abbr not in abbr_dict: abbr_dict[abbr] = []
                abbr_dict[abbr].append(tinh)
        if 'hcm' not in abbr_dict: abbr_dict['hcm'] = ['Thành phố Hồ Chí Minh']
        if 'tphcm' not in abbr_dict: abbr_dict['tphcm'] = ['Thành phố Hồ Chí Minh']
    return abbr_dict

abbr_dict = build_abbreviation_dict(df_map)

# Nạp từ điển người dùng
user_dict = {}
if not df_dict.empty:
    for _, row in df_dict.iterrows():
        chuan = row['Địa danh']
        tu_dien = str(row['Từ điển']).split(',')
        for td in tu_dien:
            if td.strip():
                user_dict[clean_address_string(td.strip())] = chuan

def fuzzy_match(text):
    # Rule 1: i <-> y
    yield text.replace('i', 'y')
    yield text.replace('y', 'i')
    # Rule 2: s <-> x, ch <-> tr
    yield text.replace('s', 'x')
    yield text.replace('x', 's')
    yield text.replace('ch', 'tr')
    yield text.replace('tr', 'ch')
    # Rule 3: Dấu hỏi <-> Ngã (Đơn giản hóa cho không dấu hoặc thay thế thô)
    yield text.replace('ả', 'ã').replace('ủ', 'ũ').replace('ỉ', 'ĩ').replace('ỏ', 'õ').replace('ẻ', 'ẽ')
    yield text.replace('ã', 'ả').replace('ũ', 'ủ').replace('ĩ', 'ỉ').replace('õ', 'ỏ').replace('ẽ', 'ẻ')

# Tạo danh sách chuẩn để map (Tạo ra một bộ lookup nhanh)
master_lookup = {}
for _, row in df_map.iterrows():
    c_p = clean_address_string(str(row['Phường/Xã cũ']))
    n_p = clean_address_string(str(row['Phường/Xã mới']))
    master_lookup[c_p] = row['Phường/Xã mới']
    master_lookup[n_p] = row['Phường/Xã mới']

# ==========================================
# HÀM CẬP NHẬT TỪ ĐIỂN LÊN GOOGLE SHEET
# ==========================================
def update_dictionary(standard_word, typo_word):
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID).worksheet("Dict")
    
    # Tìm xem địa danh chuẩn đã có trong cột A chưa
    records = sheet.get_all_records()
    found_idx = -1
    for i, r in enumerate(records):
        if str(r.get('Địa danh', '')).strip() == standard_word:
            found_idx = i + 2 # +2 vì index bắt đầu từ 0 và có 1 dòng header
            break
            
    if found_idx != -1:
        # Đã có -> Nối thêm vào cột B (Từ điển)
        current_dict = sheet.acell(f'B{found_idx}').value or ""
        new_dict = f"{current_dict}, {typo_word}" if current_dict else typo_word
        sheet.update_acell(f'B{found_idx}', new_dict)
    else:
        # Chưa có -> Append dòng mới
        sheet.append_row([standard_word, typo_word])
        
    st.cache_data.clear() # Xóa cache để lần sau load bản mới

# ==========================================
# CẤU TRÚC GIAO DIỆN (3 TAB)
# ==========================================
tab1, tab2, tab3 = st.tabs(["🔍 TRA CỨU DANH MỤC", "📁 XỬ LÝ FILE", "🧠 HUẤN LUYỆN TỪ ĐIỂN"])

# ----------------- TAB 1: TRA CỨU -----------------
with tab1:
    st.markdown("### 🔍 Tra cứu danh mục hành chính")
    chieu_tra_cuu = st.radio("Chọn chiều tra cứu:", ["Từ Cũ sang Mới", "Từ Mới truy ngược Cũ"], horizontal=True)
    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
    
    if not df_map.empty:
        if chieu_tra_cuu == "Từ Cũ sang Mới":
            c1, c2, c3 = st.columns(3)
            
            with c1:
                tinh_opts = ["-- Tất cả --"] + sorted(df_map['Tỉnh/Thành phố cũ'].dropna().unique().tolist())
                tinh = st.selectbox("1. Tỉnh/Thành phố (Cũ):", options=tinh_opts)
                
            with c2:
                huyen_opts = ["-- Tất cả --"] + sorted(df_map[df_map['Tỉnh/Thành phố cũ'] == tinh]['Quận/Huyện cũ'].dropna().unique().tolist()) if tinh != "-- Tất cả --" else ["-- Tất cả --"]
                huyen = st.selectbox("2. Quận/Huyện (Cũ):", options=huyen_opts)
                
            with c3:
                xa_opts = ["-- Tất cả --"] + sorted(df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen)]['Phường/Xã cũ'].dropna().unique().tolist()) if huyen != "-- Tất cả --" and tinh != "-- Tất cả --" else ["-- Tất cả --"]
                xa = st.selectbox("3. Phường/Xã (Cũ):", options=xa_opts)
                
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔍 Bắt đầu Tra cứu", use_container_width=True):
                if tinh == "-- Tất cả --":
                    st.warning("Vui lòng chọn ít nhất Tỉnh/Thành phố để tra cứu!")
                elif huyen == "-- Tất cả --" and xa == "-- Tất cả --":
                    # Chỉ chọn cấp Tỉnh
                    tinh_moi = df_map[df_map['Tỉnh/Thành phố cũ'] == tinh]['Tỉnh/Thành phố mới'].iloc[0]
                    st.info(f"📍 **Tỉnh/Thành phố tương đương:** {tinh_moi}")
                elif xa == "-- Tất cả --":
                    # Chọn tới cấp Quận/Huyện
                    kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen)]
                    st.success(f"📍 Các đơn vị mới thuộc {huyen}:")
                    st.dataframe(
                        kq[['Phường/Xã cũ', 'Tỉnh/Thành phố mới', 'Phường/Xã mới', 'Trạng thái sáp nhập']],
                        use_container_width=True, hide_index=True
                    )
                else:
                    # Chọn chi tiết tới Phường/Xã
                    kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen) & (df_map['Phường/Xã cũ'] == xa)].iloc[0]
                    st.info(f"📍 **Tỉnh/Thành phố mới:** {kq['Tỉnh/Thành phố mới']} \n\n📍 **Phường/Xã mới:** {kq['Phường/Xã mới']} ({kq['Trạng thái sáp nhập']})")

        else: # Chiều Mới -> Cũ
            c1, c2 = st.columns(2)
            
            with c1:
                tinh_moi_opts = ["-- Tất cả --"] + sorted(df_map['Tỉnh/Thành phố mới'].dropna().unique().tolist())
                tinh_moi = st.selectbox("1. Tỉnh/Thành phố (Mới):", options=tinh_moi_opts)
                
            with c2:
                xa_moi_opts = ["-- Tất cả --"] + sorted(df_map[df_map['Tỉnh/Thành phố mới'] == tinh_moi]['Phường/Xã mới'].dropna().unique().tolist()) if tinh_moi != "-- Tất cả --" else ["-- Tất cả --"]
                xa_moi = st.selectbox("2. Phường/Xã (Mới):", options=xa_moi_opts)
                
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔍 Truy vết Nguồn gốc", use_container_width=True):
                if tinh_moi == "-- Tất cả --":
                    st.warning("Vui lòng chọn ít nhất Tỉnh/Thành phố để tra cứu!")
                elif xa_moi == "-- Tất cả --":
                    # Chỉ chọn cấp Tỉnh
                    tinh_cu_list = df_map[df_map['Tỉnh/Thành phố mới'] == tinh_moi]['Tỉnh/Thành phố cũ'].unique()
                    tinh_cu_str = ", ".join(tinh_cu_list)
                    st.info(f"📍 **Nguồn gốc Tỉnh/Thành phố cũ:** {tinh_cu_str}")
                else:
                    # Chọn chi tiết tới Phường/Xã mới
                    kq = df_map[(df_map['Tỉnh/Thành phố mới'] == tinh_moi) & (df_map['Phường/Xã mới'] == xa_moi)]
                    st.success(f"📍 3 cấp đơn vị cũ cấu thành nên Phường/Xã này:")
                    st.dataframe(
                        kq[['Tỉnh/Thành phố cũ', 'Quận/Huyện cũ', 'Phường/Xã cũ']],
                        use_container_width=True, hide_index=True
                    )

# ----------------- TAB 2: XỬ LÝ FILE -----------------
with tab2:
    uploaded_file = st.file_uploader("Kéo thả file Excel của bạn vào đây", type=['xlsx', 'xls'])
    if uploaded_file is not None:
        df_input = pd.read_excel(uploaded_file)
        addr_col = st.selectbox("Chọn cột chứa Địa Chỉ:", options=df_input.columns)
        
        if st.button("🚀 Bắt đầu chuyển đổi", use_container_width=True):
            results, notes = [], []
            new_pending = set()
            
            with st.spinner("Đang áp dụng bộ Rule-based và quét Master Data..."):
                for idx, row in df_input.iterrows():
                    raw_val = str(row[addr_col])
                    cleaned = clean_address_string(raw_val)
                    
                    # 1. Dò trong Master Data (Cũ hoặc Mới đều OK)
                    if cleaned in master_lookup:
                        results.append(master_lookup[cleaned])
                        notes.append("")
                        continue
                        
                    # 2. Dò trong Từ điển tự học
                    if cleaned in user_dict:
                        results.append(user_dict[cleaned])
                        notes.append("Map từ Từ điển")
                        continue
                        
                    # 3. Dò bằng Fuzzy Logic
                    matched_fuzzy = False
                    for variant in fuzzy_match(cleaned):
                        if variant in master_lookup:
                            results.append(master_lookup[variant])
                            notes.append("Tự động sửa lỗi chính tả")
                            matched_fuzzy = True
                            break
                    
                    if matched_fuzzy: continue
                        
                    # 4. Không tìm thấy -> Cho vào Pending
                    results.append(raw_val)
                    notes.append("⚠️ Cần xác nhận")
                    if cleaned: new_pending.add(raw_val) # Lưu nguyên gốc để hiển thị
            
            df_input['[Hệ Thống] Địa chỉ Mới'] = results
            df_input['[Hệ Thống] Cảnh báo'] = notes
            
            # Cập nhật danh sách cần dạy vào session
            st.session_state.pending_words.update(new_pending)
            
            st.success("Xử lý hoàn tất!")
            st.dataframe(df_input)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_input.to_excel(writer, index=False)
            st.download_button(label="📥 Tải xuống File đã xử lý", data=output.getvalue(), file_name="DiaChi_DaChuyenDoi.xlsx")
            
            if new_pending:
                st.warning(f"Phát hiện {len(new_pending)} địa chỉ lạ. Hãy chuyển sang Tab 'Huấn luyện Từ điển' để dạy hệ thống!")

# ----------------- TAB 3: HUẤN LUYỆN -----------------
with tab3:
    st.markdown("### Dạy hệ thống nhận diện từ sai")
    if not st.session_state.pending_words:
        st.success("Tuyệt vời! Hiện không có từ lạ nào cần huấn luyện.")
    else:
        st.write("Chọn các từ bạn muốn nạp vào bộ nhớ:")
        # List tất cả Phường Xã chuẩn để chọn
        all_standard_wards = sorted(df_map['Phường/Xã cũ'].dropna().unique().tolist() + df_map['Phường/Xã mới'].dropna().unique().tolist())
        all_standard_wards = list(set(all_standard_wards))
        
        for word in list(st.session_state.pending_words):
            col_a, col_b, col_c = st.columns([2, 3, 1])
            with col_a:
                st.text_input("Từ sai (Pending):", value=word, disabled=True, key=f"err_{word}")
            with col_b:
                # Có thể gõ để search trong selectbox của streamlit
                chosen_standard = st.selectbox("Chọn địa danh chuẩn (hoặc để trống):", options=["-- Bỏ qua --"] + all_standard_wards, key=f"std_{word}")
            with col_c:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Lưu", key=f"btn_{word}"):
                    if chosen_standard != "-- Bỏ qua --":
                        with st.spinner("Đang lưu lên Google Sheet..."):
                            update_dictionary(chosen_standard, word)
                            st.session_state.pending_words.remove(word)
                            st.success(f"Đã lưu: {word} -> {chosen_standard}")
                            time.sleep(1)
                            st.rerun()
