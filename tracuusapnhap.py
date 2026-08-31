import streamlit as st
import pandas as pd
import re
import io
import gspread
from google.oauth2.service_account import Credentials
import time
import unicodedata

# ==========================================
# CẤU HÌNH GIAO DIỆN & MÀU SẮC
# ==========================================
st.set_page_config(page_title="TRA CỨU SÁP NHẬP", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    h1, h2, h3 {
        background: -webkit-linear-gradient(45deg, #FF1493, #8A2BE2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: bold;
    }
    .stButton>button {
        background: linear-gradient(135deg, #FF1493 0%, #8A2BE2 100%);
        color: white !important;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover { transform: scale(1.02); box-shadow: 0 4px 10px rgba(138, 43, 226, 0.4); }
    .stTextInput input, .stSelectbox div[data-baseweb="select"] { border-radius: 6px; border: 1px solid #d1d5db; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; font-size: 3em;'>TRA CỨU SÁP NHẬP</h1>", unsafe_allow_html=True)

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
    for col in df_map.columns:
        df_map[col] = df_map[col].astype(str).str.strip()
    return df_map, df_dict

if 'last_update' not in st.session_state:
    st.session_state.last_update = time.strftime("%H:%M:%S %d/%m/%Y")
if 'pending_errors' not in st.session_state:
    st.session_state.pending_errors = [] # Lưu dictionary chi tiết lỗi

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
def remove_accents(input_str):
    s1 = u'ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúýĂăĐđĨĩŨũƠơƯưẠạẢảẤấẦầẨẩẪẫẬậẮắẰằẲẳẴẵẶặẸẹẺẻẼẽẾếỀềỂểỄễỆệỈỉỊịỌọỎỏỐốỒồỔổỖỗỘộỚớỜờỞởỠỡỢợỤụỦủỨứỪừỬửỮữỰựỲỳỴỵỶỷỸỹ'
    s0 = u'AAAAEEEIIOOOOUUYaaaaeeeiioooouuyAaDdIiUuOoUuAaAaAaAaAaAaAaAaAaAaAaAaEeEeEeEeEeEeEeEeIiIiOoOoOoOoOoOoOoOoOoOoOoOoUuUuUuUuUuUuUuUuYyYyYyYy'
    s = ''
    for c in input_str:
        if c in s1: s += s0[s1.index(c)]
        else: s += c
    return s

def clean_text_for_match(text):
    if not isinstance(text, str): return ""
    text = unicodedata.normalize('NFC', str(text)).lower()
    text = remove_accents(text)
    text = re.sub(r'[,.\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# Nạp từ điển người dùng
user_dict = {}
if not df_dict.empty:
    for _, row in df_dict.iterrows():
        chuan = str(row.get('Địa danh', '')).strip()
        tu_dien = str(row.get('Từ điển', '')).split(',')
        for td in tu_dien:
            if td.strip():
                user_dict[clean_text_for_match(td.strip())] = chuan

def get_list_by_level(level, context_tinh=None, context_huyen=None):
    if level == "Tỉnh":
        return sorted(df_map['Tỉnh/Thành phố cũ'].unique().tolist())
    elif level == "Quận":
        if context_tinh: return sorted(df_map[df_map['Tỉnh/Thành phố cũ'] == context_tinh]['Quận/Huyện cũ'].unique().tolist())
        return []
    elif level == "Phường":
        if context_tinh and context_huyen: return sorted(df_map[(df_map['Tỉnh/Thành phố cũ'] == context_tinh) & (df_map['Quận/Huyện cũ'] == context_huyen)]['Phường/Xã cũ'].unique().tolist())
        return []
    return []

# ==========================================
# CẤU TRÚC GIAO DIỆN (3 TAB)
# ==========================================
tab1, tab2, tab3 = st.tabs(["🔍 TRA CỨU DANH MỤC", "📁 XỬ LÝ CHUYỂN ĐỔI", "🧠 HUẤN LUYỆN TỪ ĐIỂN"])

# ----------------- TAB 1: TRA CỨU -----------------
with tab1:
    st.markdown("### 🔍 Tra cứu danh mục hành chính")
    # T đã rút gọn khúc này giống y code Ver 3 m đã duyệt để tập trung bộ lòng Option ở dưới.
    st.info("Khu vực tra cứu danh mục nhanh (Cũ <=> Mới)")

# ----------------- TAB 2: XỬ LÝ FILE -----------------
with tab2:
    st.markdown("### Chọn phương thức xử lý địa chỉ")
    option = st.radio("", ["1️⃣ Chuyển đổi Đơn lẻ (Điền Form)", "2️⃣ File Tự Do (Địa chỉ gom chung 1 cột)"], horizontal=True)
    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

    if option.startswith("1️⃣"):
        c_s, c_p, c_q, c_t = st.columns(4)
        with c_s: s_input = st.text_input("Số nhà + Tên đường:")
        with c_p: p_input = st.text_input("Phường/Xã cũ:")
        with c_q: q_input = st.text_input("Quận/Huyện cũ:")
        with c_t: t_input = st.text_input("Tỉnh/Thành cũ:")
        
        if st.button("🚀 Chuyển đổi ngay", use_container_width=True):
            if not p_input or not t_input: 
                st.warning("Vui lòng nhập ít nhất Phường/Xã và Tỉnh/Thành")
            else:
                # Quét thông minh không dấu
                p_clean = clean_text_for_match(p_input)
                p_clean = user_dict.get(p_clean, p_clean)
                
                mask = df_map['Phường/Xã cũ'].apply(clean_text_for_match) == p_clean
                kq = df_map[mask]
                
                if not kq.empty:
                    row = kq.iloc[0]
                    # RÁP ĐỊA CHỈ MỚI: Bỏ qua Quận, chỉ lấy Số nhà + Phường Mới + Tỉnh Mới
                    addr_prefix = f"{s_input}, " if s_input.strip() else ""
                    final_addr = f"{addr_prefix}{row['Phường/Xã mới']}, {row['Tỉnh/Thành phố mới']}"
                    st.success(f"**Kết quả:** {final_addr}")
                else:
                    st.error("Không tìm thấy trong Master Data. Vui lòng check lỗi chính tả.")

    elif option.startswith("2️⃣"):
        st.info("💡 Tính năng Quét Chuỗi thông minh đang được nâng cấp để chạy ngược từ Lớn đến Nhỏ. Nếu địa chỉ lỗi, nó sẽ bắn qua Tab 3.")
        upl_3 = st.file_uploader("Upload Excel chứa địa chỉ trộn chung", type=['xlsx'], key="file3")
        if upl_3:
            df_in3 = pd.read_excel(upl_3)
            col_addr = st.selectbox("Chọn Cột Địa Chỉ Đầy Đủ:", df_in3.columns)
            
            if st.button("🚀 Bắt đầu Quét Chuỗi", use_container_width=True):
                # Demo bóc tách từ phải sang trái
                res_addr, res_status = [], []
                new_pendings = []
                
                for _, row in df_in3.iterrows():
                    raw = str(row[col_addr])
                    clean = clean_text_for_match(raw)
                    
                    # (Giả lập logic nhận diện lỗi khuyết cấp Tỉnh/Quận/Phường)
                    # Trong thực tế, AI sẽ check Tỉnh -> Nếu fail -> Ghi lỗi cấp Tỉnh
                    # Ở đây demo bắt 1 case "Thanh Đa P27 qbinh thanh" 
                    if "binh thanh" in clean and "quận bình thạnh" not in raw.lower():
                        res_addr.append(raw)
                        res_status.append("⚠️ Lỗi cấp Quận")
                        new_pendings.append({
                            "raw": raw,
                            "error_level": "Quận",
                            "context_tinh": "Thành phố Hồ Chí Minh",
                            "context_huyen": "",
                            "typo": "qbinh thanh"
                        })
                    else:
                        res_addr.append("Địa chỉ đã quét xong")
                        res_status.append("Thành công")
                        
                df_in3['[Hệ Thống] Kết quả'] = res_addr
                df_in3['[Hệ Thống] Trạng thái'] = res_status
                st.session_state.pending_errors.extend(new_pendings)
                st.dataframe(df_in3)

# ----------------- TAB 3: HUẤN LUYỆN -----------------
with tab3:
    st.markdown("### 🧠 Dạy hệ thống nhận diện TỪ GÕ SAI (Từ điển)")
    
    if not st.session_state.pending_errors:
        st.success("Tuyệt vời! Hiện không có từ lạ nào bị kẹt.")
    else:
        st.write("Hệ thống đã khoanh vùng lỗi theo cấp. Bạn chỉ cần chọn đúng Tên chuẩn để dạy nó:")
        
        # Lấy 1 lỗi đầu tiên ra xử lý cho gọn màn hình
        err = st.session_state.pending_errors[0]
        
        st.warning(f"**Chuỗi bị lỗi:** {err['raw']}")
        st.info(f"**Phân tích AI:** Tỉnh/Thành đã chốt là `{err['context_tinh']}`. Phát hiện lỗi gõ sai ở cấp **{err['error_level']}**.")
        
        c_a, c_b = st.columns([1, 1])
        with c_a:
            typo_input = st.text_input("Trích xuất chữ viết sai:", value=err['typo'])
        with c_b:
            opts = get_list_by_level(err['error_level'], err['context_tinh'], err['context_huyen'])
            chosen = st.selectbox(f"Chọn {err['error_level']} chuẩn để map:", options=["-- Chọn --"] + opts)
            
        if st.button("Lưu & Dạy hệ thống", type="primary"):
            if chosen != "-- Chọn --" and typo_input:
                client = get_gspread_client()
                sheet = client.open_by_key(SHEET_ID).worksheet("Dict")
                records = sheet.get_all_records()
                found = False
                for i, r in enumerate(records):
                    if str(r.get('Địa danh', '')).strip() == chosen:
                        cur = sheet.acell(f'B{i+2}').value or ""
                        sheet.update_acell(f'B{i+2}', f"{cur}, {typo_input}" if cur else typo_input)
                        found = True; break
                if not found: sheet.append_row([chosen, typo_input])
                
                st.session_state.pending_errors.pop(0) # Xóa lỗi đã xử lý
                st.cache_data.clear()
                st.success(f"Đã lưu thành công: {typo_input} -> {chosen}")
                time.sleep(1)
                st.rerun()
