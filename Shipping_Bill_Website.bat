@echo off
REM ==============================
REM Batch file to run Streamlit App
REM ==============================

REM Set your Google API Key as an environment variable
set GOOGLE_API_KEY=AIzaSyCKxF3Vv2GUtOyS_-VdxdjGVUNqA4u6wyU

REM Navigate to your project folder
cd /d "C:\path\to\your\project"

REM Force Streamlit to open automatically in the browser
python -m streamlit run main.py --server.headless false

pause
