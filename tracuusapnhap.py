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

# Bỏ ttl=0 để Form Tab 1 không bị lag mỗi lần click!
@st.cache_data
def load_data():
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID)
    df_map = pd.DataFrame(sheet.worksheet("Mapping").get_all_records())
    df_dict = pd.DataFrame(sheet.worksheet("Dict").get_all_records())
    
    # [VACCINE 1]: Ép chuẩn Unicode NFC toàn tập để chống lệch bảng mã (Trị bệnh Case 2: Phường Tân Phú)
    def normalize_nfc(text):
        if pd.isna(text): return ""
        return unicodedata.normalize('NFC', str(text)).strip()
        
    for col in df_map.columns:
        df_map[col] = df_map[col].apply(normalize_nfc)
        
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

# [VACCINE 2]: Hàm che chữ tàng hình (chỉ che trong chuỗi tìm kiếm, không đụng chuỗi gốc)
def mask_core_in_clean_str(text, entity):
    if not entity: return text
    core = extract_core_name(entity)
    if not core: return text
    # Che mờ bằng khoảng trắng để không dính từ ghép ma "Thuận An + Bình Dương -> An Bình"
    return re.sub(r'\b' + re.escape(core) + r'\b', lambda m: ' ' * len(m.group(0)), text)

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

# ==========================================
# AI 8.0 (BẢN GỐC): SLIDING WINDOW & NÉ BẪY SỐ NHÀ
# ==========================================
def smart_find_entity(entity_list, text, entity_type="None"):
    candidates = []
    for orig in entity_list:
        if pd.isna(orig) or str(orig).strip() == '': continue
        clean_full = clean_text_for_match(str(orig))
        core = extract_core_name(clean_full)
        candidates.append((orig, clean_full, core))
        
    candidates.sort(key=lambda x: len(x[2]), reverse=True)
    
    # LỚP 1: Tiền tố rõ ràng (Quét lùi bằng reversed)
    for orig, full, core in candidates:
        if entity_type == "Quan": prefix = r'\b(quan|q|huyen|h|tx|thi xa)\b\.?\s*'
        elif entity_type == "Phuong": prefix = r'\b(phuong|p|xa|x|tt|thi tran)\b\.?\s*'
        elif entity_type == "Tinh": prefix = r'\b(tinh|thanh pho|tp)\b\.?\s*'
        else: prefix = r''
        
        if prefix:
            matches = list(re.finditer(prefix + re.escape(core) + r'\b', text))
            if matches: return orig
            
    # LỚP 2: Lõi độc lập (Quét Lùi Sliding Window)
    for orig, full, core in candidates:
        if core.isdigit(): continue # Quận 1, Phường 2 thì bắt buộc phải dính Lớp 1
        
        matches = list(re.finditer(r'\b' + re.escape(core) + r'\b', text))
        if matches:
            for match in reversed(matches):
                preceding = text[:match.start()].strip()
                
                # Né bẫy: Cướp cờ Quận/Phường chéo (VD Q. Tân Phú)
                conflict_match = re.search(r'\b(quan|q|huyen|h|tx|thi xa|phuong|p|xa|x|tt|thi tran|tinh|tp)\b\.?$', preceding)
                if conflict_match:
                    p_found = conflict_match.group(1).replace('.', '')
                    is_valid = False
                    if entity_type == "Quan" and p_found in ['quan', 'q', 'huyen', 'h', 'tx', 'thi xa']: is_valid = True
                    elif entity_type == "Phuong" and p_found in ['phuong', 'p', 'xa', 'x', 'tt', 'thi tran']: is_valid = True
                    elif entity_type == "Tinh" and p_found in ['tinh', 'tp', 'thanh pho']: is_valid = True
                    if not is_valid: continue
                
                # Né bẫy: Tên đường nằm sát số nhà (223 Tân Thành)
                if re.match(r'^(số\s+)?(đường\s+)?\d+[a-z]?(/\d+)*[,\s-]*$', preceding):
                    continue
                    
                return orig
    return None

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
                    kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh) & (df_map['Quận/Huyện cũ'] == huyen) & (df_map['Phường/Xã cũ'] == xa)]
                    p_moi_list = kq['Phường/Xã mới'].dropna().unique().tolist()
                    t_moi = kq['Tỉnh/Thành phố mới'].iloc[0]
                    p_str = " HOẶC ".join(p_moi_list)
                    
                    st.info(f"📍 **Tỉnh/Thành phố mới:** {t_moi} \n\n📍 **Phường/Xã mới:** {p_str}")
                    if len(p_moi_list) > 1:
                        st.warning("⚠️ LƯU Ý: Phường/Xã cũ này đã được tách ra thành nhiều Phường/Xã mới. Vui lòng kiểm tra lại để chọn chính xác.")

        else:
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
    option = st.radio("", ["1️⃣ Chuyển đổi Đơn lẻ", "2️⃣ File Mẫu Chuẩn", "3️⃣ File Tự Do (Bản chuẩn 8.0 + Sửa tay)"], horizontal=True)
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
            if p_val == "-- Chọn --": st.warning("Vui lòng chọn đầy đủ lộ trình đến cấp Phường/Xã!")
            else:
                kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == t_val) & (df_map['Quận/Huyện cũ'] == q_val) & (df_map['Phường/Xã cũ'] == p_val)]
                addr_prefix = f"{s_input.strip()}, " if s_input.strip() else ""
                
                p_moi_list = kq['Phường/Xã mới'].dropna().unique().tolist()
                t_moi_list = kq['Tỉnh/Thành phố mới'].dropna().unique().tolist()
                
                p_str = " HOẶC ".join(p_moi_list)
                t_str = t_moi_list[0] if t_moi_list else ""
                
                final_addr = f"{addr_prefix}{p_str}, {t_str}"
                if len(p_moi_list) > 1: st.warning(f"**Kết quả:** {final_addr}\n\n*⚠️ Nhớ kiểm tra lại vì Phường cũ tách ra nhiều Phường mới.*")
                else: st.success(f"**Kết quả:** {final_addr}")

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
                        mask = (df_map_core['p_core'] == extract_core_name(p_clean)) & (df_map_core['q_core'] == extract_core_name(str(row_in[col_d]))) & (df_map_core['t_core'] == extract_core_name(str(row_in[col_p])))
                        kq = df_map[mask]
                        if not kq.empty:
                            s_val = str(row_in[col_s]).strip()
                            addr_prefix = f"{s_val}, " if s_val and s_val.lower() != 'nan' else ""
                            p_moi_list = kq['Phường/Xã mới'].dropna().unique().tolist()
                            t_moi = kq['Tỉnh/Thành phố mới'].iloc[0]
                            p_str = " HOẶC ".join(p_moi_list)
                            
                            res_addr.append(f"{addr_prefix}{p_str}, {t_moi}")
                            if len(p_moi_list) > 1: res_status.append("⚠️ Thành công (Nhớ kiểm tra lại vì tách Phường)")
                            else: res_status.append("Thành công")
                        else:
                            res_addr.append(""); res_status.append("⚠️ Không nhận diện được")
                            
                df_in2['[Hệ Thống] Kết quả (2 cấp)'] = res_addr
                df_in2['[Hệ Thống] Trạng thái'] = res_status
                
                # [VACCINE 3]: Bảng tương tác để sửa lỗi
                st.info("💡 BẢNG KẾT QUẢ TƯƠNG TÁC: Click đúp vào ô bất kỳ để SỬA TAY những địa chỉ bạn thấy chưa chuẩn, sau đó bấm nút Tải xuống.")
                edited_df2 = st.data_editor(df_in2, use_container_width=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer: edited_df2.to_excel(writer, index=False)
                st.download_button("📥 Tải File Đã Xử Lý (Bao gồm ô tự sửa)", data=output.getvalue(), file_name="Ket_Qua_Opt2.xlsx")

    elif option.startswith("3️⃣"):
        st.info("💡 AI 8.0: Xóa bỏ bẫy Số nhà, Không cắt đứt đuôi dấu phẩy, Dò Mới/Cũ chuẩn như con người.")
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
                        notes_dict = {}
                        
                        # DỌN RÁC NGOẶC ĐƠN: Cũ xóa sạch, Mới giữ chữ
                        def repl(m):
                            text = m.group(0)
                            text_lower = text.lower()
                            text_unaccent = remove_accents(text_lower)
                            if 'cũ' in text_lower or (re.search(r'\bcu\b', text_unaccent) and re.search(r'\b(quan|phuong|q|p|tinh|tp|huyen|h|xa|x)\b', text_unaccent)):
                                return ''
                            elif 'mới' in text_lower or re.search(r'\bmoi\b', text_unaccent):
                                return text.strip('()')
                            else:
                                key = f"__NOTE_{len(notes_dict)}__"
                                notes_dict[key] = text
                                return key

                        raw_str_processed = re.sub(r'\([^)]+\)', repl, raw_str)
                        raw_str_processed = re.sub(r'\b(cũ|cu)\b', '', raw_str_processed, flags=re.IGNORECASE).strip()
                        
                        clean_str = clean_text_for_match(raw_str_processed)
                        
                        for typo, correct in user_dict.items():
                            clean_str = clean_str.replace(typo, clean_text_for_match(correct))
                            
                        is_new_address = False
                        final_tinh = None; final_xa = None; final_huyen = None
                        status_warning = ""
                        
                        # --- 1. QUÉT ĐỊA CHỈ MỚI TRƯỚC ---
                        tinh_moi_unique = df_map['Tỉnh/Thành phố mới'].dropna().unique()
                        for abbr, full_names in abbr_dict.items():
                            if re.search(r'\b' + abbr + r'\b$', clean_str): final_tinh = full_names[0]; break
                            
                        if not final_tinh:
                            final_tinh = smart_find_entity(tinh_moi_unique, clean_str, "Tinh")
                            
                        if final_tinh and final_tinh in tinh_moi_unique:
                            # Che Tỉnh để trị dứt điểm Case 1 (Từ ghép ma "Thuận An + Bình Dương")
                            clean_str_masked = mask_core_in_clean_str(clean_str, final_tinh)
                            ds_xa_moi = df_map[df_map['Tỉnh/Thành phố mới'] == final_tinh]['Phường/Xã mới'].dropna().unique()
                            found_x_moi = smart_find_entity(ds_xa_moi, clean_str_masked, "Phuong")
                            if found_x_moi:
                                is_new_address = True
                                final_xa = found_x_moi
                                
                        # --- 2. NẾU KHÔNG PHẢI MỚI -> QUÉT ĐỊA CHỈ CŨ ---
                        if not is_new_address:
                            if not final_tinh:
                                final_tinh = smart_find_entity(df_map['Tỉnh/Thành phố cũ'].dropna().unique(), clean_str, "Tinh")
                                if not final_tinh:
                                    if re.search(r'\b(hcm|tphcm)\b', clean_str): final_tinh = "Thành phố Hồ Chí Minh"
                                    elif re.search(r'\b(hn)\b', clean_str): final_tinh = "Thành phố Hà Nội"
                                
                            if not final_tinh:
                                res_addr.append(""); res_status.append("⚠️ Không nhận diện được Tỉnh")
                                new_pendings.append({"raw": raw_str, "found_tinh": None, "found_huyen": None, "found_xa": None})
                                continue
                                
                            clean_str_masked = mask_core_in_clean_str(clean_str, final_tinh)
                            ds_huyen_cu = df_map[df_map['Tỉnh/Thành phố cũ'] == final_tinh]['Quận/Huyện cũ'].dropna().unique()
                            found_h_cu = smart_find_entity(ds_huyen_cu, clean_str_masked, "Quan")
                            
                            if found_h_cu:
                                clean_str_masked_2 = mask_core_in_clean_str(clean_str_masked, found_h_cu)
                                ds_xa_cu = df_map[(df_map['Tỉnh/Thành phố cũ'] == final_tinh) & (df_map['Quận/Huyện cũ'] == found_h_cu)]['Phường/Xã cũ'].dropna().unique()
                                found_x_cu = smart_find_entity(ds_xa_cu, clean_str_masked_2, "Phuong")
                                if found_x_cu:
                                    final_huyen = found_h_cu; final_xa = found_x_cu
                                else:
                                    # KHÁCH GHI NHẦM QUẬN -> TỰ SỬA QUẬN
                                    ds_xa_cu_all = df_map[df_map['Tỉnh/Thành phố cũ'] == final_tinh]['Phường/Xã cũ'].dropna().unique()
                                    # Lấy clean_str_masked (chỉ bị che Tỉnh) để nó tự do kiếm Phường sai Quận
                                    found_x_cu_all = smart_find_entity(ds_xa_cu_all, clean_str_masked, "Phuong")
                                    if found_x_cu_all:
                                        real_huyen = df_map[(df_map['Tỉnh/Thành phố cũ'] == final_tinh) & (df_map['Phường/Xã cũ'] == found_x_cu_all)]['Quận/Huyện cũ'].iloc[0]
                                        final_huyen = real_huyen; final_xa = found_x_cu_all
                                        status_warning = "⚠️ Nhớ kiểm tra lại (Hệ thống tự động sửa Quận do mâu thuẫn)"
                                    else:
                                        res_addr.append(""); res_status.append(f"⚠️ Lỗi Phường/Xã của {found_h_cu}")
                                        new_pendings.append({"raw": raw_str, "error_level": "Phường", "context_tinh": final_tinh, "context_huyen": found_h_cu, "typo": ""})
                                        continue
                            else:
                                # KHÁCH BỎ QUÊN QUẬN -> TỰ SUY TỪ PHƯỜNG
                                ds_xa_cu_all = df_map[df_map['Tỉnh/Thành phố cũ'] == final_tinh]['Phường/Xã cũ'].dropna().unique()
                                found_x_cu = smart_find_entity(ds_xa_cu_all, clean_str_masked, "Phuong")
                                if found_x_cu:
                                    ds_h_cua_x = df_map[(df_map['Tỉnh/Thành phố cũ'] == final_tinh) & (df_map['Phường/Xã cũ'] == found_x_cu)]['Quận/Huyện cũ'].dropna().unique()
                                    if len(ds_h_cua_x) == 1:
                                        final_huyen = ds_h_cua_x[0]; final_xa = found_x_cu
                                        status_warning = "⚠️ Nhớ kiểm tra lại (Quận bị khuyết, tự suy ra từ Phường)"
                                    else:
                                        res_addr.append(""); res_status.append(f"⚠️ Trùng tên Phường '{found_x_cu}' ở nhiều Quận")
                                        new_pendings.append({"raw": raw_str, "found_tinh": final_tinh, "found_huyen": None, "found_xa": found_x_cu})
                                        continue
                                else:
                                    res_addr.append(""); res_status.append(f"⚠️ Lỗi Quận/Huyện của {final_tinh}")
                                    new_pendings.append({"raw": raw_str, "found_tinh": final_tinh, "found_huyen": None, "found_xa": None})
                                    continue

                        # --- BƯỚC 3: CẮT CHUỖI SỐ NHÀ CHUẨN XÁC ---
                        idx_xa = get_cut_index(raw_str_processed, final_xa, "Phuong")
                        idx_huyen = get_cut_index(raw_str_processed, final_huyen, "Quan") if not is_new_address else len(raw_str_processed)
                        idx_tinh = get_cut_index(raw_str_processed, final_tinh, "Tinh")
                        
                        cut_idx = min([idx for idx in [idx_xa, idx_huyen, idx_tinh] if idx > 0] + [len(raw_str_processed)])
                        
                        so_nha = raw_str_processed[:cut_idx].strip(' ,.-')
                        
                        # Khôi phục ngoặc đơn ghi chú (nếu có)
                        for k, v in list(notes_dict.items()):
                            if k in so_nha:
                                so_nha = so_nha.replace(k, v)
                                del notes_dict[k]
                                
                        addr_prefix = f"{so_nha}, " if so_nha else ""
                        
                        if is_new_address:
                            kq = df_map[(df_map['Tỉnh/Thành phố mới'] == final_tinh) & (df_map['Phường/Xã mới'] == final_xa)].iloc[0]
                            final_addr = f"{addr_prefix}{kq['Phường/Xã mới']}, {kq['Tỉnh/Thành phố mới']}"
                            if notes_dict: final_addr += " " + " ".join(notes_dict.values())
                            res_addr.append(final_addr)
                            res_status.append(status_warning if status_warning else "Đã là địa chỉ Mới (Giữ nguyên)")
                        else:
                            kq = df_map[(df_map['Tỉnh/Thành phố cũ'] == final_tinh) & (df_map['Quận/Huyện cũ'] == final_huyen) & (df_map['Phường/Xã cũ'] == final_xa)]
                            p_moi_list = kq['Phường/Xã mới'].dropna().unique().tolist()
                            
                            final_addr = f"{addr_prefix}{' HOẶC '.join(p_moi_list)}, {kq.iloc[0]['Tỉnh/Thành phố mới']}"
                            if notes_dict: final_addr += " " + " ".join(notes_dict.values())
                            res_addr.append(final_addr)
                            
                            if len(p_moi_list) > 1: res_status.append("⚠️ Thành công (Nhớ kiểm tra lại vì Phường cũ tách ra nhiều Phường mới)")
                            else: res_status.append(status_warning if status_warning else "Thành công (Đã chuyển đổi)")

                df_in3['[Hệ Thống] Kết quả (2 cấp)'] = res_addr
                df_in3['[Hệ Thống] Trạng thái'] = res_status
                
                if new_pendings:
                    st.session_state.pending_errors.extend(new_pendings)
                    st.error(f"Phát hiện {len(new_pendings)} địa chỉ lỗi. Hãy qua Tab 3 để điền form huấn luyện hoặc Sửa tay ngay trong bảng dưới đây!")
                else:
                    st.success("Tuyệt vời! File đã được AI dọn sạch bóng không trượt phát nào!")
                    
                st.info("💡 BẢNG KẾT QUẢ TƯƠNG TÁC: Click đúp vào ô bất kỳ để SỬA TAY những địa chỉ bạn thấy chưa chuẩn, sau đó bấm nút Tải xuống.")
                edited_df3 = st.data_editor(df_in3, use_container_width=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer: edited_df3.to_excel(writer, index=False)
                st.download_button("📥 Tải File Đã Xử Lý (Bao gồm cả các ô bạn đã sửa tay)", data=output.getvalue(), file_name="Ket_Qua_Opt3.xlsx")

# ----------------- TAB 3: HUẤN LUYỆN -----------------
with tab3:
    st.markdown("### 🧠 Dạy hệ thống nhận diện TỪ GÕ SAI (Từ điển)")
    if not st.session_state.pending_errors:
        st.success("Tuyệt vời! Hiện không có từ lạ nào bị kẹt.")
    else:
        err = st.session_state.pending_errors[0]
        st.warning(f"**Chuỗi bị lỗi:** {err['raw']}")
        st.write("Hệ thống đã khoanh vùng những thực thể nó tìm được. Bạn hãy bổ sung những phần còn thiếu:")
        
        loai_dc = st.radio("Loại địa chỉ của chuỗi trên:", ["📍 Địa chỉ CŨ (3 Cấp)", "📍 Địa chỉ MỚI (2 Cấp)"], horizontal=True)
        is_cu = "CŨ" in loai_dc
        
        st.markdown("<br>", unsafe_allow_html=True)
        cols = st.columns(3) if is_cu else st.columns(2)
        
        tinh_opts_raw = df_map['Tỉnh/Thành phố cũ'].dropna().unique() if is_cu else df_map['Tỉnh/Thành phố mới'].dropna().unique()
        tinh_opts = ["-- Vui lòng chọn --"] + sorted([str(x) for x in tinh_opts_raw])
        def_tinh = str(err.get('found_tinh'))
        idx_tinh = tinh_opts.index(def_tinh) if def_tinh in tinh_opts else 0
        tinh_sel = cols[0].selectbox("1. Tỉnh/Thành phố:", tinh_opts, index=idx_tinh)
        
        huyen_sel = "-- Vui lòng chọn --"
        if is_cu:
            huyen_opts = ["-- Vui lòng chọn --"]
            if tinh_sel != "-- Vui lòng chọn --":
                huyen_opts += sorted([str(x) for x in df_map[df_map['Tỉnh/Thành phố cũ'] == tinh_sel]['Quận/Huyện cũ'].dropna().unique()])
            def_huyen = str(err.get('found_huyen'))
            idx_huyen = huyen_opts.index(def_huyen) if def_huyen in huyen_opts else 0
            huyen_sel = cols[1].selectbox("2. Quận/Huyện:", huyen_opts, index=idx_huyen)
            
        xa_opts = ["-- Vui lòng chọn --"]
        if is_cu:
            if tinh_sel != "-- Vui lòng chọn --" and huyen_sel != "-- Vui lòng chọn --":
                xa_opts += sorted([str(x) for x in df_map[(df_map['Tỉnh/Thành phố cũ'] == tinh_sel) & (df_map['Quận/Huyện cũ'] == huyen_sel)]['Phường/Xã cũ'].dropna().unique()])
        else:
            if tinh_sel != "-- Vui lòng chọn --":
                xa_opts += sorted([str(x) for x in df_map[df_map['Tỉnh/Thành phố mới'] == tinh_sel]['Phường/Xã mới'].dropna().unique()])
                
        def_xa = str(err.get('found_xa'))
        idx_xa = xa_opts.index(def_xa) if def_xa in xa_opts else 0
        
        if is_cu: xa_sel = cols[2].selectbox("3. Phường/Xã:", xa_opts, index=idx_xa)
        else: xa_sel = cols[1].selectbox("2. Phường/Xã:", xa_opts, index=idx_xa)

        st.markdown("---")
        st.write("🎯 **CHỈ ĐỊNH TỪ VIẾT SAI VÀO TỪ ĐIỂN:**")
        c_typo, c_map = st.columns(2)
        with c_typo: typo_input = st.text_input("Người dùng copy/gõ chữ bị viết sai trong câu gốc vào đây:")
        with c_map:
            map_opts = ["-- Chọn --"]
            if tinh_sel != "-- Vui lòng chọn --": map_opts.append(f"Tỉnh: {tinh_sel}")
            if is_cu and huyen_sel != "-- Vui lòng chọn --": map_opts.append(f"Quận: {huyen_sel}")
            if xa_sel != "-- Vui lòng chọn --": map_opts.append(f"Phường: {xa_sel}")
            target_map = st.selectbox("Gán chữ sai đó cho Tên chuẩn nào?", options=map_opts)
            
        c_btn1, c_btn2, _ = st.columns([2, 2, 4])
        with c_btn1:
            if st.button("💾 Lưu & Dạy hệ thống", type="primary", use_container_width=True):
                if target_map != "-- Chọn --" and typo_input:
                    chosen_entity = target_map.split(": ")[1]
                    client = get_gspread_client()
                    sheet = client.open_by_key(SHEET_ID).worksheet("Dict")
                    records = sheet.get_all_records()
                    found = False
                    for i, r in enumerate(records):
                        if str(r.get('Địa danh', '')).strip() == chosen_entity:
                            cur = sheet.acell(f'B{i+2}').value or ""
                            sheet.update_acell(f'B{i+2}', f"{cur}, {typo_input}" if cur else typo_input)
                            found = True; break
                    if not found: sheet.append_row([chosen_entity, typo_input])
                    st.success(f"Đã lưu thành công: {typo_input} -> {chosen_entity}")
                    st.session_state.pending_errors.pop(0)
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Vui lòng nhập Chữ viết sai và Chọn Tên chuẩn để gán!")
                    
        with c_btn2:
            if st.button("⏭️ Bỏ qua lỗi này", use_container_width=True):
                st.session_state.pending_errors.pop(0)
                st.rerun()
