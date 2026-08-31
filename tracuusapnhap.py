import streamlit as st
import pandas as pd
import re
import io
import time

# ==========================================
# CẤU HÌNH GIAO DIỆN & MÀU SẮC
# ==========================================
st.set_page_config(page_title="TRA CỨU SÁP NHẬP", layout="wide")

st.markdown("""
<style>
    /* Theme Hồng đậm sang Tím */
    .stApp {
        background: linear-gradient(135deg, #FF1493 0%, #8A2BE2 100%);
    }
    h1, h2, h3, h4, h5, h6, p, span, div, label {
        color: white !important;
    }
    .stButton>button {
        background-color: #ffffff;
        color: #8A2BE2 !important;
        font-weight: bold;
        border-radius: 8px;
    }
    .stButton>button:hover {
        background-color: #ffb6c1;
        color: #FF1493 !important;
    }
    /* Khung upload file */
    .stFileUploader {
        background-color: rgba(255, 255, 255, 0.2);
        border-radius: 10px;
        padding: 10px;
    }
    .stSelectbox div[data-baseweb="select"] {
        background-color: white !important;
        color: black !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; font-size: 3em;'>TRA CỨU SÁP NHẬP</h1>", unsafe_allow_html=True)

# Lấy thời gian cập nhật để m biết vừa F5 thành công
if 'last_update' not in st.session_state:
    st.session_state.last_update = time.strftime("%H:%M:%S %d/%m/%Y")

# ==========================================
# KẾT NỐI DATA GOOGLE SHEET
# ==========================================
@st.cache_data(ttl=0) # ttl=0 để nút Làm mới chạy ép buộc tải lại
def load_data():
    sheet_id = "15vjVT7KFUVj_7aawYD-leKSdzAWGNdDzZAS-GmrOtl4"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    try:
        xls = pd.ExcelFile(url)
        df_map = pd.read_excel(xls, sheet_name='Mapping')
        df_dict = pd.read_excel(xls, sheet_name='Dict')
        return df_map, df_dict
    except Exception as e:
        st.error(f"Lỗi tải dữ liệu: {e}")
        return pd.DataFrame(), pd.DataFrame()

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🔄 Cập nhật dữ liệu mới nhất (Xóa Cache)", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_update = time.strftime("%H:%M:%S %d/%m/%Y")
        st.success("Đã tải dữ liệu nóng hổi từ Google Sheet!")

st.markdown(f"<p style='text-align: center;'><i>Cập nhật lần cuối: {st.session_state.last_update}</i></p>", unsafe_allow_html=True)

df_map, df_dict = load_data()

# ==========================================
# BỘ CÔNG CỤ RULE-BASED TIỀN XỬ LÝ
# ==========================================
def clean_address_string(text):
    if not isinstance(text, str): return ""
    # 1. Lowercase
    text = text.lower()
    # 2. Xóa dấu câu (thay bằng khoảng trắng)
    text = re.sub(r'[,.\-]', ' ', text)
    # 3. Trimming khoảng trắng
    text = re.sub(r'\s+', ' ', text).strip()
    # 4. Tách Quận/Phường dính liền số (q1 -> q 1)
    text = re.sub(r'\b(q|p|f|d)(\d+)\b', r'\1 \2', text)
    # 5. Xóa tiền tố hành chính (stop-words)
    stop_words = r'\b(tỉnh|thành phố|tp|quận|q|huyện|h|thị xã|tx|phường|p|xã|x|thị trấn|tt)\b'
    text = re.sub(stop_words, '', text)
    # Xóa khoảng trắng thừa lần nữa
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def build_abbreviation_dict(df):
    """Tự động sinh bộ viết tắt (HN, HCM, TPHCM...) từ Master Data"""
    abbr_dict = {}
    if not df.empty:
        tinh_cu = df['Tỉnh/Thành phố cũ'].dropna().unique()
        for tinh in tinh_cu:
            tinh_clean = clean_address_string(tinh)
            words = tinh_clean.split()
            # VD: hà nội -> hn
            abbr = "".join([w[0] for w in words if w])
            if abbr:
                if abbr not in abbr_dict:
                    abbr_dict[abbr] = []
                abbr_dict[abbr].append(tinh)
        # Bổ sung cứng vài ca phổ biến
        if 'hcm' not in abbr_dict: abbr_dict['hcm'] = ['Thành phố Hồ Chí Minh']
        if 'tphcm' not in abbr_dict: abbr_dict['tphcm'] = ['Thành phố Hồ Chí Minh']
    return abbr_dict

abbr_dict = build_abbreviation_dict(df_map)

# Load Dict do user học vào (tách bởi dấu phẩy)
user_dict = {}
if not df_dict.empty:
    for _, row in df_dict.iterrows():
        chuan = row['Địa danh']
        tu_dien = str(row['Từ điển']).split(',')
        for td in tu_dien:
            user_dict[clean_address_string(td.strip())] = chuan

# ==========================================
# CẤU TRÚC APP: 2 TAB
# ==========================================
tab1, tab2 = st.tabs(["🔍 TRA CỨU DANH MỤC (CŨ <=> MỚI)", "📁 XỬ LÝ FILE HÀNG LOẠT (EXCEL)"])

# ----------------- TAB 1: TRA CỨU -----------------
with tab1:
    st.markdown("### Tra cứu danh mục Phường/Xã")
    chieu_tra_cuu = st.radio("Chọn chiều tra cứu:", ["Từ Cũ sang Mới", "Từ Mới truy ngược Cũ"], horizontal=True)
    
    if not df_map.empty:
        if chieu_tra_cuu == "Từ Cũ sang Mới":
            tinh = st.selectbox("Chọn Tỉnh/Thành phố (Cũ):", options=["-- Chọn --"] + sorted(df_map['Tỉnh/Thành phố cũ'].unique().tolist()))
            if tinh != "-- Chọn --":
                huyen = st.selectbox("Chọn Quận/Huyện (Cũ):", options=["-- Chọn --"] + sorted(df_map[df_map['Tỉnh/Thành phố cũ'] == tinh]['Quận/Huyện cũ'].unique().tolist()))
                if huyen != "-- Chọn --":
                    xa = st.selectbox("Chọn Phường/Xã (Cũ):", options=["-- Chọn --"] + sorted(df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen)]['Phường/Xã cũ'].unique().tolist()))
                    if xa != "-- Chọn --":
                        kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen) & (df_map['Phường/Xã cũ'] == xa)].iloc[0]
                        st.info(f"**Kết quả mới:** {kq['Phường/Xã mới']} ({kq['Trạng thái sáp nhập']})")
                        
        else: # Mới -> Cũ
            tinh = st.selectbox("Chọn Tỉnh/Thành phố (Mới):", options=["-- Chọn --"] + sorted(df_map['Tỉnh/Thành phố mới'].unique().tolist()))
            if tinh != "-- Chọn --":
                xa = st.selectbox("Chọn Phường/Xã (Mới):", options=["-- Chọn --"] + sorted(df_map[df_map['Tỉnh/Thành phố mới'] == tinh]['Phường/Xã mới'].unique().tolist()))
                if xa != "-- Chọn --":
                    kq = df_map[(df_map['Tỉnh/Thành phố mới'] == tinh) & (df_map['Phường/Xã mới'] == xa)]
                    st.write("**Các đơn vị cũ được sáp nhập tạo thành Phường/Xã này:**")
                    st.dataframe(kq[['Tỉnh/Thành phố cũ', 'Quận/Huyện cũ', 'Phường/Xã cũ']])

# ----------------- TAB 2: XỬ LÝ FILE -----------------
with tab2:
    st.markdown("### Upload File chứa địa chỉ cần chuyển đổi")
    uploaded_file = st.file_uploader("Kéo thả file Excel của bạn vào đây", type=['xlsx', 'xls'])
    
    if uploaded_file is not None:
        try:
            df_input = pd.read_excel(uploaded_file)
            st.write("Bản xem trước dữ liệu tải lên:")
            st.dataframe(df_input.head())
            
            # Chọn cột chứa địa chỉ
            addr_col = st.selectbox("Chọn cột chứa Địa Chỉ:", options=df_input.columns)
            
            if st.button("🚀 Bắt đầu chuyển đổi", use_container_width=True):
                with st.spinner("Đang áp dụng bộ Rule-based và quét Master Data..."):
                    
                    # Logic mô phỏng map (Cần khớp với dữ liệu thực tế dựa theo Rule)
                    # (Lưu ý: Logic map chuẩn chuỗi sẽ rất dài, t làm bộ khung chạy file giả lập map trực tiếp)
                    results = []
                    notes = []
                    
                    for idx, row in df_input.iterrows():
                        raw_val = str(row[addr_col])
                        cleaned = clean_address_string(raw_val)
                        
                        # Demo Map đơn giản từ Từ Điển User
                        if cleaned in user_dict:
                            results.append(f"[Từ điển] -> {user_dict[cleaned]}")
                            notes.append("")
                        else:
                            # Tạm xuất giá trị rỗng để hiển thị luồng
                            results.append("Đang chờ ráp Full Regex Logic") 
                            notes.append("Yêu cầu check map")
                    
                    df_input['[Hệ Thống] Địa chỉ Mới'] = results
                    df_input['[Hệ Thống] Cảnh báo'] = notes
                    
                    st.success("Xử lý hoàn tất!")
                    st.dataframe(df_input)
                    
                    # Nút tải file
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_input.to_excel(writer, index=False)
                    processed_data = output.getvalue()
                    
                    st.download_button(
                        label="📥 Tải xuống File đã xử lý",
                        data=processed_data,
                        file_name="DiaChi_DaChuyenDoi.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        except Exception as e:
            st.error(f"Lỗi đọc file: {e}")
