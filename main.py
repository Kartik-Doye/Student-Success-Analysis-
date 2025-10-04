import os
import io
import tempfile
import json
import re
import pandas as pd
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.document_loaders import PyPDFLoader
import base64

# ---------------- CONFIG ----------------
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError(
        "GOOGLE_API_KEY not found. Set it as an environment variable before running.\n"
        "On mac/linux: export GOOGLE_API_KEY='AIza...'\n"
        "On Windows (PowerShell): $env:GOOGLE_API_KEY='AIza...'"
    )

COLUMNS = [
    "Sr. No.", "SB NO.", "S/B Date", "LEO Date", "CUSTOMER NAME", "FINAL INVOICE NO",
    "SB. SOLAR / OTHER GOODS", "PORT CODE", "INCOTERMS", "COUNTRY", "H.S. Itch code",
    "PRODUCT GROUP", "Qty", "Unit", "FOB Value declared by us (S/B)in FC",
    "Currency of export", "Custom Exchange Rate in FC", "LEO Date Exchange Rate in in FC",
    "FOB Value as per SB in INR", "FOB Value as per LEO ex rate in INR",
    "ACTUAL FRT + INSURANC  IN FC", "Total Invoice Value in FC as per SB",
    "PAYMENT RECEIPT", "PAYMENT OUTSTANDING", "Total Invoice Value in INR as per SB",
    "SCHEME (ADV/DFIA/DRAWBACK)", "EPCG LICECE", "Drawback cap per unit in Rs. (₹)",
    "DBK %", "DRAWBACK Receivable on fob", "DRAWBCK Scrol NO", "Scroll Date",
    "DBK Realized BEFORE 31.03.2026", "SHORT REALIZATION", "BAL DBK",
    "REASONS OF BAL DBK", "REMARKS FOR ACTION TAKEN FOR RECOVERY AS ON DTD. XX.XX.2020",
    "RoDTEP%", "RoDTEP RECEIVABLE", "RoDTEP Y/N", "Transmitted Y/N",
    "RoDTEP REALIZE BEFORE 31.03.2026", "SCRIP NUMBER", "SCRIP ISSUE DATE",
    "SORT REALIZAION", "BAL RoDTEP", "REASONS OF BAL RoDTEP",
    "DBK Not Realized BUT PAYMENT OUTSTANDING > 9 MONTH",
    "Reason for BAL/SHORTFALL",
    "REMARKS FOR ACTION TAKEN FOR RECOVERY AS ON DTD.",
    "BOOKING IN SAP"
]

# ---------------- INIT GEMINI LLM ----------------
@st.cache_resource
def init_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        api_key=GOOGLE_API_KEY
    )

llm = init_llm()

# ---------------- JSON PARSING HELPERS ----------------
def _extract_json_block(text: str):
    m = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    return m.group(1) if m else None

def generate_json_from_gemini(prompt: str, retries: int = 3):
    for attempt in range(retries):
        resp = llm.invoke(prompt)
        text = resp.content if hasattr(resp, "content") else resp
        try:
            return json.loads(text)
        except Exception:
            pass
        block = _extract_json_block(text)
        if block:
            try:
                return json.loads(block)
            except Exception:
                pass
    return []

def normalize_extracted(extracted):
    if isinstance(extracted, list):
        return extracted
    if isinstance(extracted, dict):
        for v in extracted.values():
            if isinstance(v, list) and all(isinstance(i, dict) for i in v):
                return v
        return [extracted]
    return []

# ---------------- PDF -> MATERIAL ROWS ----------------
def process_single_pdf_bytes(pdf_bytes: bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes); tmp.flush(); tmp_path = tmp.name
    try:
        loader = PyPDFLoader(tmp_path)
        docs = loader.load()
        full_text = "\n".join(d.page_content for d in docs)
    finally:
        try: os.remove(tmp_path)
        except Exception: pass

    extraction_prompt = f"""
You are an expert in export compliance. Extract material-wise line items from the given Shipping Bill.
Return a JSON array where each element is a JSON object representing one material line item.

Each object MUST contain the following keys (use empty string "" where value is missing):
{COLUMNS}

Return strictly valid JSON (an array). Do not include extra commentary or text outside the JSON array.

Document:
\"\"\"{full_text}\"\"\"
"""
    extracted_raw = generate_json_from_gemini(extraction_prompt)
    rows = normalize_extracted(extracted_raw)
    cleaned_rows = []
    for r in rows:
        if not isinstance(r, dict): continue
        cleaned_rows.append({col: r.get(col, "") for col in COLUMNS})
    return cleaned_rows

def process_uploaded_pdfs(uploaded_files):
    all_rows = []; errors = []
    for f in uploaded_files:
        try:
            pdf_bytes = f.read()
            rows = process_single_pdf_bytes(pdf_bytes)
            if not rows:
                errors.append((f.name, "No material items extracted (empty response)."))
            else:
                all_rows.extend(rows)
        except Exception as e:
            errors.append((f.name, str(e)))
    return all_rows, errors

# ---------------- IMAGE HELPERS ----------------
def get_base64_of_bin_file(bin_file):
    """Convert binary file to base64 string"""
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def get_img_with_href(local_img_path, target_url, img_style=""):
    """Generate HTML for clickable image"""
    try:
        img_format = local_img_path.split('.')[-1]
        bin_str = get_base64_of_bin_file(local_img_path)
        html_code = f'''
        <a href="{target_url}" target="_blank">
            <img src="data:image/{img_format};base64,{bin_str}" style="{img_style}"/>
        </a>'''
        return html_code
    except:
        return ""

# ---------------- CUSTOM STYLING ----------------
def apply_solar_styling():
    st.markdown("""
        <style>
        /* Import Google Fonts */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700;900&display=swap');
        
        /* Global App Styling */
        .stApp {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            font-family: 'Roboto', sans-serif;
        }
        
        /* Hide Streamlit menu and footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Custom header container */
        .solar-header {
            background: linear-gradient(135deg, #E30613 0%, #B91C1C 100%);
            padding: 1.5rem 2rem;
            border-radius: 0 0 20px 20px;
            margin: -1rem -1rem 2rem -1rem;
            box-shadow: 0 4px 20px rgba(227, 6, 19, 0.3);
            position: relative;
            overflow: hidden;
        }
        
        .solar-header::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -20%;
            width: 200px;
            height: 200px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            transform: rotate(45deg);
        }
        
        .solar-header h1 {
            color: white !important;
            font-size: 2.5rem !important;
            font-weight: 900 !important;
            margin: 0 !important;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            position: relative;
            z-index: 1;
        }
        
        .solar-tagline {
            color: rgba(255, 255, 255, 0.9) !important;
            font-size: 1.1rem !important;
            font-weight: 300 !important;
            margin-top: 0.5rem !important;
            position: relative;
            z-index: 1;
        }
        
        /* Logo styling */
        .solar-logo {
            position: absolute;
            top: 20px;
            right: 30px;
            height: 60px;
            z-index: 2;
        }
        
        /* Card-style containers */
        .info-card {
            background: white;
            padding: 1.5rem;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            margin: 1rem 0;
            border-left: 4px solid #E30613;
        }
        
        .upload-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            padding: 2rem;
            border-radius: 20px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            border: 2px dashed #E30613;
            text-align: center;
            margin: 2rem 0;
        }
        
        /* Button styling */
        .stButton > button {
            background: linear-gradient(135deg, #E30613 0%, #B91C1C 100%);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 0.75rem 2rem;
            font-weight: 600;
            font-size: 1rem;
            box-shadow: 0 4px 15px rgba(227, 6, 19, 0.3);
            transition: all 0.3s ease;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(227, 6, 19, 0.4);
            background: linear-gradient(135deg, #B91C1C 0%, #E30613 100%);
        }
        
        /* File uploader styling */
        .stFileUploader > div > div {
            background: white;
            border: 2px dashed #E30613;
            border-radius: 15px;
            padding: 2rem;
        }
        
        /* Success/Error message styling */
        .stSuccess {
            background: linear-gradient(135deg, #10B981 0%, #059669 100%);
            color: white;
            border-radius: 10px;
            padding: 1rem;
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
        }
        
        .stWarning {
            background: linear-gradient(135deg, #F59E0B 0%, #D97706 100%);
            color: white;
            border-radius: 10px;
            padding: 1rem;
            box-shadow: 0 4px 15px rgba(245, 158, 11, 0.3);
        }
        
        /* Table styling */
        .dataframe {
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }
        
        .dataframe th {
            background: #E30613 !important;
            color: white !important;
            font-weight: 600 !important;
            padding: 1rem !important;
            text-align: center !important;
        }
        
        .dataframe td {
            padding: 0.75rem !important;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .dataframe tr:nth-child(even) {
            background: #f8f9fa;
        }
        
        .dataframe tr:hover {
            background: rgba(227, 6, 19, 0.05);
        }
        
        /* Download button styling */
        .stDownloadButton > button {
            background: linear-gradient(135deg, #059669 0%, #10B981 100%);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 0.75rem 2rem;
            font-weight: 600;
            box-shadow: 0 4px 15px rgba(5, 150, 105, 0.3);
        }
        
        /* Spinner styling */
        .stSpinner {
            color: #E30613 !important;
        }
        
        /* Info box styling */
        .stInfo {
            background: linear-gradient(135deg, #3B82F6 0%, #1E40AF 100%);
            color: white;
            border-radius: 10px;
            padding: 1rem;
            box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
        }
        
        /* Footer */
        .solar-footer {
            background: #1f2937;
            color: white;
            text-align: center;
            padding: 2rem;
            margin-top: 3rem;
            border-radius: 20px 20px 0 0;
        }
        
        .solar-footer h3 {
            color: #E30613 !important;
            margin-bottom: 1rem !important;
        }
        
        /* Responsive design */
        @media (max-width: 768px) {
            .solar-header h1 {
                font-size: 2rem !important;
            }
            
            .solar-logo {
                height: 40px;
                top: 15px;
                right: 15px;
            }
            
            .upload-card {
                padding: 1rem;
            }
        }
        </style>
    """, unsafe_allow_html=True)

def create_header():
    # Try to load and display the logo
    logo_html = ""
    if os.path.exists("assets/solar_logo.png"):
        logo_html = get_img_with_href("assets/solar_logo.png", "https://solargroup.com", 
                                     "height: 60px; margin-left: 20px;")
    elif os.path.exists("solar_logo.png"):
        logo_html = get_img_with_href("solar_logo.png", "https://solargroup.com", 
                                     "height: 60px; margin-left: 20px;")
    
    st.markdown(f"""
        <div class="solar-header">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center;">
                    {logo_html}
                    <div style="margin-left: 20px;">
                        <h1>📄 Shipping Bill Extractor</h1>
                        <div class="solar-tagline">Material-wise Extraction | Power to Propel</div>
                    </div>
                </div>
                <div style="text-align: right; color: rgba(255,255,255,0.8); font-size: 0.9rem;">
                    <div style="font-weight: 600;">Solar Industries India Limited</div>
                    <div>Export Compliance Solutions</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def create_info_section():
    # Add the spiral logo if available
    spiral_logo_html = ""
    if os.path.exists("assets/spiral_logo.png"):
        spiral_logo_html = f'''
        <div style="text-align: center; margin: 2rem 0;">
            <img src="data:image/png;base64,{get_base64_of_bin_file("assets/spiral_logo.png")}" 
                 style="height: 80px; opacity: 0.8;">
        </div>'''
    elif os.path.exists("spiral_logo.png"):
        spiral_logo_html = f'''
        <div style="text-align: center; margin: 2rem 0;">
            <img src="data:image/png;base64,{get_base64_of_bin_file("spiral_logo.png")}" 
                 style="height: 80px; opacity: 0.8;">
        </div>'''
    
    st.markdown(f"""
        <div class="info-card">
            <h3 style="color: #E30613; margin-bottom: 1rem;">🎯 How It Works</h3>
            {spiral_logo_html}
    """, unsafe_allow_html=True)

    # Display instructions in plain text using st.markdown
    st.markdown("""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem;">
            <div style="padding: 1rem; background: #f8f9fa; border-radius: 10px;">
                <h4 style="color: #E30613; margin-bottom: 0.5rem;">1️⃣ Upload</h4>
                <p style="margin: 0; color: #6b7280;">Select one or more Shipping Bill PDF files</p>
            </div>
            <div style="padding: 1rem; background: #f8f9fa; border-radius: 10px;">
                <h4 style="color: #E30613; margin-bottom: 0.5rem;">2️⃣ Process</h4>
                <p style="margin: 0; color: #6b7280;">AI extracts material-wise line items automatically</p>
            </div>
            <div style="padding: 1rem; background: #f8f9fa; border-radius: 10px;">
                <h4 style="color: #E30613; margin-bottom: 0.5rem;">3️⃣ Download</h4>
                <p style="margin: 0; color: #6b7280;">Get structured Excel output with all data</p>
            </div>
        </div>
    """, unsafe_allow_html=True) # Keep unsafe_allow_html for the styling div

    st.markdown("</div>", unsafe_allow_html=True) # Close the info-card div

def create_footer():
    st.markdown("""
        <div class="solar-footer">
            <h3>Solar Industries India Limited</h3>
            <p style="margin: 0.5rem 0; opacity: 0.8;">Leading manufacturer of Industrial Explosives and Propellants</p>
            <div style="display: flex; justify-content: center; gap: 2rem; margin-top: 1.5rem; flex-wrap: wrap;">
                <div style="text-align: center;">
                    <div style="font-weight: 600; color: #E30613;">📍 Address</div>
                    <div style="font-size: 0.9rem; opacity: 0.8;">Solar House, 14, Kachmer<br>Amravati Road, Nagpur<br>Maharashtra 440023</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-weight: 600; color: #E30613;">📞 Contact</div>
                    <div style="font-size: 0.9rem; opacity: 0.8;">+91 7028593763<br>+91 712 6917129(129)</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-weight: 600; color: #E30613;">✉️ Email</div>
                    <div style="font-size: 0.9rem; opacity: 0.8;">ritik.ingole@solargroup.com<br>www.solargroup.com</div>
                </div>
            </div>
            <hr style="margin: 2rem 0; opacity: 0.3;">
            <p style="margin: 0; opacity: 0.6; font-size: 0.8rem;">
                © 2024 Solar Industries India Limited. All rights reserved. | Power to Propel
            </p>
        </div>
    """, unsafe_allow_html=True)

# ---------------- STREAMLIT UI ----------------
def main():
    # Page configuration
    st.set_page_config(
        page_title="Solar Industries - Shipping Bill Extractor",
        page_icon="🚢",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Apply custom styling
    apply_solar_styling()
    
    # Create header
    create_header()
    
    # Create info section
    create_info_section()
    
    # Main content area
    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
            <div style="text-align: center; margin-bottom: 2rem;">
                <h3 style="color: #E30613; margin-bottom: 1rem;">📄 Upload Shipping Bills</h3>
                <p style="color: #6b7280; margin-bottom: 2rem;">
                    Select one or more PDF files containing Shipping Bill documents.<br>
                    Our AI will extract material-wise line items automatically.
                </p>
            </div>
        """, unsafe_allow_html=True)
        
        uploaded = st.file_uploader(
            "Choose PDF files",
            type=["pdf"],
            accept_multiple_files=True,
            help="Upload multiple Shipping Bill PDF files for batch processing"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    if uploaded:
        # Show uploaded files info
        st.markdown("### 📋 Uploaded Files")
        files_info = []
        total_size = 0
        for file in uploaded:
            file_size = len(file.getvalue()) / 1024 / 1024  # MB
            total_size += file_size
            files_info.append({
                "File Name": file.name,
                "Size (MB)": f"{file_size:.2f}",
                "Type": file.type
            })
        
        files_df = pd.DataFrame(files_info)
        st.dataframe(files_df, use_container_width=True)
        
        st.info(f"📊 Total files: {len(uploaded)} | Total size: {total_size:.2f} MB")
        
        # Process button
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            process_btn = st.button(
                "🚀 Process All Files",
                use_container_width=True,
                help="Click to start AI-powered extraction process"
            )
        
        if process_btn:
            # Processing with progress
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner("🔄 Processing your files with AI... This may take a few moments."):
                status_text.text(f"Processing {len(uploaded)} files...")
                
                rows, errors = process_uploaded_pdfs(uploaded)
                
                progress_bar.progress(100)
                status_text.text("✅ Processing complete!")
            
            # Results section
            if rows:
                df = pd.DataFrame(rows, columns=COLUMNS)
                df["Sr. No."] = range(1, len(df) + 1)
                
                # Success metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📄 Files Processed", len(uploaded))
                with col2:
                    st.metric("📊 Records Extracted", len(df))
                with col3:
                    st.metric("✅ Success Rate", f"{((len(uploaded)-len(errors))/len(uploaded)*100):.1f}%")
                with col4:
                    st.metric("🔄 Processing Time", "~30s/file")
                
                st.success("🎉 Extraction completed successfully! Your data is ready for download.")
                
                # Data preview
                st.markdown("### 📋 Extracted Data Preview")
                st.dataframe(df, use_container_width=True, height=400)
                
                # Download section
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    towrite = io.BytesIO()
                    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
                        df.to_excel(writer, index=False, sheet_name="Material_Wise_Data")
                        
                        # Add summary sheet
                        summary_data = {
                            "Metric": ["Total Records", "Total Files", "Processing Date", "Extracted Columns"],
                            "Value": [len(df), len(uploaded), pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), len(COLUMNS)]
                        }
                        pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name="Summary")
                    
                    towrite.seek(0)
                    
                    st.download_button(
                        "📥 Download Complete Excel Report",
                        data=towrite.getvalue(),
                        file_name=f"Solar_Shipping_Bill_Extract_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            else:
                st.error("❌ No data was extracted from the uploaded files. Please check the file format and try again.")
            
            # Show errors if any
            if errors:
                with st.expander("⚠️ Processing Errors", expanded=False):
                    st.warning(f"Some files encountered issues during processing:")
                    for name, msg in errors:
                        st.markdown(f"- **{name}**: `{msg}`")
    else:
        st.info("👆 Please upload one or more Shipping Bill PDF files to begin processing.")
    
    # Footer
    create_footer()

if __name__ == "__main__":
    main()