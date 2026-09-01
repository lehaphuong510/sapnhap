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
    st.session_state.pending_errors = []

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
    text = re.sub(r'\b(q|quan|p|phuong|h|huyen|x|xa|tx|tt)(\d+)\b', r'\1 \2', text)
    text = re.sub(r'[,.\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_core_name(text):
    text = clean_text_for_match(text)
    stop_words = r'^(tinh|thanh pho|tp|quan|q|huyen|h|thi xa|tx|phuong|p|xa|x|thi tran|tt)\s+'
    return re.sub(stop_words, '', text).strip()

def build_abbreviation_dict(df):
    abbr_dict = {}
    if not df.empty:
        tinh_cu = df['Tỉnh/Thành phố cũ'].dropna().unique()
        for tinh in tinh_cu:
            tinh_clean = clean_text_for_match(str(tinh))
            words = tinh_clean.split()
            abbr = "".join([w[0] for w in words if w])
            if abbr:
                if abbr not in abbr_dict: abbr_dict[abbr] = []
                abbr_dict[abbr].append(tinh)
        if 'hcm' not in abbr_dict: abbr_dict['hcm'] = ['Thành phố Hồ Chí Minh']
        if 'tphcm' not in abbr_dict: abbr_dict['tphcm'] = ['Thành phố Hồ Chí Minh']
        if 'hn' not in abbr_dict: abbr_dict['hn'] = ['Thành phố Hà Nội']
    return abbr_dict

abbr_dict = build_abbreviation_dict(df_map)

user_dict = {}
if not df_dict.empty:
    for _, row in df_dict.iterrows():
        chuan = str(row.get('Địa danh', '')).strip()
        tu_dien = str(row.get('Từ điển', '')).split(',')
        for td in tu_dien:
            if td.strip(): user_dict[clean_text_for_match(td.strip())] = chuan

def get_list_by_level(level, context_tinh=None, context_huyen=None):
    if level == "Tỉnh": return sorted(df_map['Tỉnh/Thành phố cũ'].unique().tolist())
    elif level == "Quận": return sorted(df_map[df_map['Tỉnh/Thành phố cũ'] == context_tinh]['Quận/Huyện cũ'].unique().tolist()) if context_tinh else []
    elif level == "Phường": return sorted(df_map[(df_map['Tỉnh/Thành phố cũ'] == context_tinh) & (df_map['Quận/Huyện cũ'] == context_huyen)]['Phường/Xã cũ'].unique().tolist()) if context_tinh and context_huyen else []
    return []

# AI Dò tìm thực thể: Bắt bẫy chữ & số cực chuẩn
def smart_find_entity(entity_list, text, entity_type="None"):
    candidates = []
    for orig in entity_list:
        if pd.isna(orig) or str(orig).strip() == '': continue
        clean_full = clean_text_for_match(str(orig))
        core = extract_core_name(clean_full)
        candidates.append((orig, clean_full, core))
        
    candidates.sort(key=lambda x: len(x[2]), reverse=True)
    
    for orig, full, core in candidates:
        if re.search(r'\b' + full.replace(' ', r'\s+') + r'\b', text): return orig
        if core.isdigit() and entity_type != "Tinh":
            # Nếu là Số: Bắt buộc phải có Tiền tố đi kèm để tránh nhận nhầm Số nhà
            if entity_type == "Quan": prefix = r'\b(quan|q|huyen|h|tx|thi xa)\s+'
            elif entity_type == "Phuong": prefix = r'\b(phuong|p|xa|x|tt|thi tran)\s+'
            else: prefix = r'\b(quan|q|huyen|h|tx|thi xa|phuong|p|xa|x|tt|thi tran)\s+'
            if re.search(prefix + core + r'\b', text): return orig
        else:
            if core and re.search(r'\b' + core.replace(' ', r'\s+') + r'\b', text): return orig
    return None

# AI Cắt chuỗi thông minh (Loại bỏ triệt để P, xã, phường bị dư)
def get_cut_index(raw_str, entity_orig, entity_type):
    if not entity_orig: return len(raw_str)
    core = extract_core_name(clean_text_for_match(str(entity_orig)))
    raw_unaccent = remove_accents(raw_str).lower()
    
    prefixes = ""
    if entity_type == "Phuong": prefixes = r'(?:phuong|p|xa|x|thi tran|tt)\b\.?\s*'
    elif entity_type == "Quan": prefixes = r'(?:quan|q|huyen|h|thi xa|tx)\b\.?\s*'
    elif entity_type == "Tinh": prefixes = r'(?:tinh|thanh pho|tp)\b\.?\s*'
    
    if core.isdigit(): pattern = r'\b' + prefixes + core + r'\b'
    else: pattern = r'\b(?:' + prefixes + r')?' + core.replace(' ', r'\s+') + r'\b'
        
    matches = list(re.finditer(pattern, raw_unaccent))
    if matches: return matches[-1].start()
    
    idx = raw_unaccent.find(core)
    if idx != -1:
        prefix_match = re.search(r'\b(?:p|q|x|h)\b\.?\s*$', raw_unaccent[:idx])
        if prefix_match: return prefix_match.start()
        return idx
    return len(raw_str)

# ==========================================
# CẤU TRÚC GIAO DIỆN (3 TAB)
# ==========================================
tab1, tab2, tab3 = st.tabs(["🔍 TRA CỨU DANH MỤC", "📁 XỬ LÝ CHUYỂN ĐỔI", "🧠 HUẤN LUYỆN TỪ ĐIỂN"])

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
                if tinh == "-- Tất cả --": st.warning("Vui lòng chọn ít nhất Tỉnh/Thành phố để tra cứu!")
                elif huyen == "-- Tất cả --" and xa == "-- Tất cả --":
                    st.info(f"📍 **Tỉnh/Thành phố tương đương:** {df_map[df_map['Tỉnh/Thành phố cũ'] == tinh]['Tỉnh/Thành phố mới'].iloc[0]}")
                elif xa == "-- Tất cả --":
                    kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen)]
                    st.success(f"📍 Các đơn vị mới thuộc {huyen}:")
                    st.dataframe(kq[['Phường/Xã cũ', 'Tỉnh/Thành phố mới', 'Phường/Xã mới']], use_container_width=True, hide_index=True)
                else:
                    kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen) & (df_map['Phường/Xã cũ'] == xa)].iloc[0]
                    st.info(f"📍 **Tỉnh/Thành phố mới:** {kq['Tỉnh/Thành phố mới']} \n\n📍 **Phường/Xã mới:** {kq['Phường/Xã mới']}")

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
                if tinh_moi == "-- Tất cả --": st.warning("Vui lòng chọn ít nhất Tỉnh/Thành phố để tra cứu!")
                elif xa_moi == "-- Tất cả --":
                    st.info(f"📍 **Nguồn gốc Tỉnh/Thành phố cũ:** {', '.join(df_map[df_map['Tỉnh/Thành phố mới'] == tinh_moi]['Tỉnh/Thành phố cũ'].unique())}")
                else:
                    kq = df_map[(df_map['Tỉnh/Thành phố mới'] == tinh_moi) & (df_map['Phường/Xã mới'] == xa_moi)]
                    st.success(f"📍 3 cấp đơn vị cũ cấu thành nên Phường/Xã này:")
                    st.dataframe(kq[['Tỉnh/Thành phố cũ', 'Quận/Huyện cũ', 'Phường/Xã cũ']], use_container_width=True, hide_index=True)

# ----------------- TAB 2: XỬ LÝ FILE -----------------
with tab2:
    st.markdown("### Chọn phương thức xử lý địa chỉ")
    option = st.radio("", [
        "1️⃣ Chuyển đổi Đơn lẻ (Điền Form)", 
        "2️⃣ File Mẫu Chuẩn (Tách sẵn cột Phường, Quận, Tỉnh)", 
        "3️⃣ File Tự Do (Địa chỉ gom chung 1 cột)"
    ], horizontal=True)
    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

    if option.startswith("1️⃣"):
        c_t, c_q, c_p, c_s = st.columns(4)
        with c_t:
            tinh_opts = ["-- Chọn --"] + sorted(df_map['Tỉnh/Thành phố cũ'].dropna().unique().tolist())
            t_val = st.selectbox("1. Tỉnh/Thành cũ:", options=tinh_opts)
        with c_q:
            huyen_opts = ["-- Chọn --"] + sorted(df_map[df_map['Tỉnh/Thành phố cũ'] == t_val]['Quận/Huyện cũ'].dropna().unique().tolist()) if t_val != "-- Chọn --" else ["-- Chọn --"]
            q_val = st.selectbox("2. Quận/Huyện cũ:", options=huyen_opts)
        with c_p:
            xa_opts = ["-- Chọn --"] + sorted(df_map[(df_map['Tỉnh/Thành phố cũ'] == t_val) & (df_map['Quận/Huyện cũ'] == q_val)]['Phường/Xã cũ'].dropna().unique().tolist()) if q_val != "-- Chọn --" else ["-- Chọn --"]
            p_val = st.selectbox("3. Phường/Xã cũ:", options=xa_opts)
        with c_s: 
            s_input = st.text_input("4. Số nhà + Tên đường:")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Chuyển đổi ngay", use_container_width=True):
            if p_val == "-- Chọn --": 
                st.warning("Vui lòng chọn đầy đủ lộ trình đến cấp Phường/Xã!")
            else:
                kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == t_val) & (df_map['Quận/Huyện cũ'] == q_val) & (df_map['Phường/Xã cũ'] == p_val)].iloc[0]
                addr_prefix = f"{s_input.strip()}, " if s_input.strip() else ""
                st.success(f"**Kết quả (Chuẩn 2 cấp):** {addr_prefix}{kq['Phường/Xã mới']}, {kq['Tỉnh/Thành phố mới']}")

    elif option.startswith("2️⃣"):
        st.info("💡 Hệ thống tự động lột lõi, xử lý hoàn hảo dữ liệu thiếu chữ 'Phường', 'Quận'.")
        
        template_df = pd.DataFrame(columns=["Số nhà + Tên đường", "Phường/Xã", "Quận/Huyện", "Tỉnh/Thành phố"])
        template_io = io.BytesIO()
        with pd.ExcelWriter(template_io, engine='xlsxwriter') as writer: template_df.to_excel(writer, index=False)
        st.download_button(label="⬇️ Tải file Excel mẫu (Template)", data=template_io.getvalue(), file_name="Mau_Chuan.xlsx")
        st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)

        upl_2 = st.file_uploader("Upload Excel (đã điền theo mẫu)", type=['xlsx'], key="file2")
        if upl_2:
            df_in2 = pd.read_excel(upl_2)
            c1, c2, c3, c4 = st.columns(4)
            with c1: col_s = st.selectbox("Cột Số nhà/Đường:", df_in2.columns)
            with c2: col_w = st.selectbox("Cột Phường/Xã:", df_in2.columns)
            with c3: col_d = st.selectbox("Cột Quận/Huyện:", df_in2.columns)
            with c4: col_p = st.selectbox("Cột Tỉnh/Thành:", df_in2.columns)
            
            if st.button("🚀 Bắt đầu Quét File", use_container_width=True):
                res_addr, res_status = [], []
                with st.spinner("Đang tra cứu dữ liệu Master..."):
                    df_map_core = df_map.copy()
                    df_map_core['p_core'] = df_map_core['Phường/Xã cũ'].apply(extract_core_name)
                    df_map_core['q_core'] = df_map_core['Quận/Huyện cũ'].apply(extract_core_name)
                    df_map_core['t_core'] = df_map_core['Tỉnh/Thành phố cũ'].apply(extract_core_name)

                    for _, row_in in df_in2.iterrows():
                        raw_p = str(row_in[col_w])
                        p_clean = user_dict.get(clean_text_for_match(raw_p), clean_text_for_match(raw_p))
                        
                        mask = (df_map_core['p_core'] == extract_core_name(p_clean)) & \
                               (df_map_core['q_core'] == extract_core_name(str(row_in[col_d]))) & \
                               (df_map_core['t_core'] == extract_core_name(str(row_in[col_p])))
                        kq = df_map[mask]
                        
                        if not kq.empty:
                            s_val = str(row_in[col_s]).strip()
                            addr_prefix = f"{s_val}, " if s_val and s_val.lower() != 'nan' else ""
                            res_addr.append(f"{addr_prefix}{kq.iloc[0]['Phường/Xã mới']}, {kq.iloc[0]['Tỉnh/Thành phố mới']}")
                            res_status.append("Thành công")
                        else:
                            res_addr.append("")
                            res_status.append("⚠️ Không nhận diện được")
                            
                df_in2['[Hệ Thống] Kết quả (2 cấp)'] = res_addr
                df_in2['[Hệ Thống] Trạng thái'] = res_status
                st.dataframe(df_in2)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_in2.to_excel(writer, index=False)
                st.download_button("📥 Tải File Đã Xử Lý", data=output.getvalue(), file_name="Ket_Qua_Opt2.xlsx")

    elif option.startswith("3️⃣"):
        st.info("💡 AI 4.5: Xử lý Ngoặc đơn, Tránh Bẫy Số Nhà & Tự Cắt Chuỗi Thông Minh 100%.")
        upl_3 = st.file_uploader("Upload Excel chứa địa chỉ trộn chung", type=['xlsx'], key="file3")
        
        if upl_3:
            df_in3 = pd.read_excel(upl_3)
            col_addr = st.selectbox("Chọn Cột Địa Chỉ Đầy Đủ:", df_in3.columns)
            
            if st.button("🚀 Bắt đầu Quét Chuỗi AI", use_container_width=True):
                res_addr, res_status = [], []
                new_pendings = []
                
                with st.spinner("Đang Săn Lùng Địa Chỉ..."):
                    for _, row in df_in3.iterrows():
                        raw_str = str(row[col_addr])
                        
                        # XỬ LÝ NGOẶC ĐƠN THÔNG MINH
                        notes_dict = {}
                        def repl(m):
                            text = m.group(0)
                            text_lower = text.lower()
                            text_unaccent = remove_accents(text_lower)
                            # Nếu có chữ "cũ" -> Xóa vĩnh viễn
                            if 'cũ' in text_lower or (re.search(r'\bcu\b', text_unaccent) and re.search(r'\b(quan|phuong|q|p|tinh|tp|huyen|h|xa|x)\b', text_unaccent)):
                                return ''
                            else:
                                # Nếu là ngoặc đơn ghi chú (ko có cũ) -> Giấu đi để AI khỏi nhầm, giữ lại khúc cuối
                                key = f"__NOTE_{len(notes_dict)}__"
                                notes_dict[key] = text
                                return key

                        raw_str_processed = re.sub(r'\([^)]+\)', repl, raw_str)
                        
                        clean_str = clean_text_for_match(raw_str_processed)
                        for typo, correct in user_dict.items():
                            clean_str = clean_str.replace(typo, clean_text_for_match(correct))
                            
                        # 1. Tìm Tỉnh
                        found_tinh = None
                        for abbr, full_names in abbr_dict.items():
                            if re.search(r'\b' + abbr + r'\b', clean_str):
                                found_tinh = full_names[0]; break
                        if not found_tinh:
                            found_tinh = smart_find_entity(df_map['Tỉnh/Thành phố cũ'].unique(), clean_str, "Tinh")
                            
                        if not found_tinh:
                            res_addr.append(""); res_status.append("⚠️ Không nhận diện được Tỉnh")
                            new_pendings.append({"raw": raw_str, "error_level": "Tỉnh", "context_tinh": "", "context_huyen": "", "typo": raw_str})
                            continue
                            
                        # 2. Tìm Quận
                        ds_huyen = df_map[df_map['Tỉnh/Thành phố cũ'] == found_tinh]['Quận/Huyện cũ'].unique()
                        found_huyen = smart_find_entity(ds_huyen, clean_str, "Quan")
                        
                        found_xa_final = None
                        is_new_address = False
                        
                        # 3. Tìm Phường & Suy luận logic
                        if not found_huyen:
                            ds_xa_moi = df_map[df_map['Tỉnh/Thành phố cũ'] == found_tinh]['Phường/Xã mới'].unique()
                            found_xa_moi = smart_find_entity(ds_xa_moi, clean_str, "Phuong")
                            
                            if found_xa_moi:
                                found_xa_final = found_xa_moi; is_new_address = True
                            else:
                                ds_xa_cu = df_map[df_map['Tỉnh/Thành phố cũ'] == found_tinh]['Phường/Xã cũ'].unique()
                                found_xa_cu = smart_find_entity(ds_xa_cu, clean_str, "Phuong")
                                if found_xa_cu:
                                    ds_huyen_cua_xa = df_map[(df_map['Tỉnh/Thành phố cũ'] == found_tinh) & (df_map['Phường/Xã cũ'] == found_xa_cu)]['Quận/Huyện cũ'].unique()
                                    if len(ds_huyen_cua_xa) == 1:
                                        found_huyen = ds_huyen_cua_xa[0]
                                        found_xa_final = found_xa_cu
                                    else:
                                        res_addr.append(""); res_status.append(f"⚠️ Trùng tên Phường '{found_xa_cu}' ở nhiều Quận")
                                        continue
                                else:
                                    res_addr.append(""); res_status.append(f"⚠️ Lỗi Phường/Xã của {found_tinh}")
                                    new_pendings.append({"raw": raw_str, "error_level": "Phường", "context_tinh": found_tinh, "context_huyen": "", "typo": ""})
                                    continue
                        else:
                            ds_xa_cu = df_map[(df_map['Tỉnh/Thành phố cũ'] == found_tinh) & (df_map['Quận/Huyện cũ'] == found_huyen)]['Phường/Xã cũ'].unique()
                            found_xa_final = smart_find_entity(ds_xa_cu, clean_str, "Phuong")
                            if not found_xa_final:
                                res_addr.append(""); res_status.append(f"⚠️ Lỗi Phường/Xã của {found_huyen}")
                                new_pendings.append({"raw": raw_str, "error_level": "Phường", "context_tinh": found_tinh, "context_huyen": found_huyen, "typo": ""})
                                continue

                        # 4. CHỐT KẾT QUẢ VÀ TÁCH SỐ NHÀ CHUẨN XÁC NHẤT
                        idx_xa = get_cut_index(raw_str_processed, found_xa_final, "Phuong")
                        idx_huyen = get_cut_index(raw_str_processed, found_huyen, "Quan")
                        idx_tinh = get_cut_index(raw_str_processed, found_tinh, "Tinh")
                        
                        cut_idx = min([idx for idx in [idx_xa, idx_huyen, idx_tinh] if idx > 0] + [len(raw_str_processed)])
                        
                        if cut_idx == len(raw_str_processed): so_nha = raw_str_processed.strip(' ,.-')
                        else: so_nha = raw_str_processed[:cut_idx].strip(' ,.-')
                        
                        # Khôi phục các ghi chú (ngoặc đơn) nằm trong số nhà
                        for k, v in list(notes_dict.items()):
                            if k in so_nha:
                                so_nha = so_nha.replace(k, v)
                                del notes_dict[k]
                                
                        addr_prefix = f"{so_nha}, " if so_nha else ""
                        
                        if is_new_address:
                            kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == found_tinh) & (df_map['Phường/Xã mới'] == found_xa_final)].iloc[0]
                            final_addr = f"{addr_prefix}{kq['Phường/Xã mới']}, {kq['Tỉnh/Thành phố mới']}"
                            res_status.append("Đã là địa chỉ Mới (Giữ nguyên)")
                        else:
                            kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == found_tinh) & (df_map['Quận/Huyện cũ'] == found_huyen) & (df_map['Phường/Xã cũ'] == found_xa_final)].iloc[0]
                            final_addr = f"{addr_prefix}{kq['Phường/Xã mới']}, {kq['Tỉnh/Thành phố mới']}"
                            res_status.append("Thành công (Đã chuyển đổi)")
                            
                        # Gắn lại phần ghi chú bị đẩy xuống cuối câu
                        if notes_dict: final_addr += " " + " ".join(notes_dict.values())
                        res_addr.append(final_addr)

                df_in3['[Hệ Thống] Kết quả (2 cấp)'] = res_addr
                df_in3['[Hệ Thống] Trạng thái'] = res_status
                
                if new_pendings:
                    st.session_state.pending_errors.extend(new_pendings)
                    st.error(f"Phát hiện {len(new_pendings)} địa chỉ lỗi. Hãy qua Tab 3 để huấn luyện!")
                else:
                    st.success("Tuyệt vời! File đã được AI dọn sạch bóng không trượt phát nào!")
                    
                st.dataframe(df_in3)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_in3.to_excel(writer, index=False)
                st.download_button("📥 Tải File Đã Xử Lý", data=output.getvalue(), file_name="Ket_Qua_Opt3.xlsx")

# ----------------- TAB 3: HUẤN LUYỆN -----------------
with tab3:
    st.markdown("### 🧠 Dạy hệ thống nhận diện TỪ GÕ SAI (Từ điển)")
    if not st.session_state.pending_errors:
        st.success("Tuyệt vời! Hiện không có từ lạ nào bị kẹt.")
    else:
        st.write("Hệ thống đã khoanh vùng lỗi theo cấp. Bạn chỉ cần chọn đúng Tên chuẩn để dạy nó:")
        err = st.session_state.pending_errors[0]
        
        st.warning(f"**Chuỗi bị lỗi:** {err['raw']}")
        st.info(f"**Phân tích AI:** Tỉnh/Thành chốt là `{err['context_tinh']}`. Lỗi cấp **{err['error_level']}**.")
        
        c_a, c_b = st.columns([1, 1])
        with c_a: typo_input = st.text_input("Trích xuất chữ viết sai:", value=err['typo'])
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
                
                st.session_state.pending_errors.pop(0)
                st.cache_data.clear()
                st.success(f"Đã lưu thành công: {typo_input} -> {chosen}")
                time.sleep(1)
                st.rerun()
