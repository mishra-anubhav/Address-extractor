import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import BytesIO
import ast
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import time

# Optional: rotate between multiple API keys (must be from separate paid accounts to truly parallelize)
OPENAI_KEYS = [
    st.secrets["openai_api_key"],
    # Add more keys here if you have them
]

def get_client(thread_id):
    key = OPENAI_KEYS[thread_id % len(OPENAI_KEYS)]
    return OpenAI(api_key=key)

# --- UI Styling ---
st.set_page_config(page_title="📬 GPT-4o Address Extractor", layout="centered")

st.markdown(
    """
    <style>
    html, body, [class*="css"]  {
        font-family: 'Segoe UI', sans-serif;
    }
    .main-title {
        background: linear-gradient(90deg, rgba(37,150,190,1) 0%, rgba(15,100,180,1) 100%);
        color: white;
        padding: 1.2rem;
        border-radius: 8px;
        text-align: center;
        font-size: 1.8rem;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.25rem;
        margin-top: 1.5rem;
        padding-bottom: 0.2rem;
        border-bottom: 2px solid #2596be;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="main-title">📬 GPT-4o Powered Address Extractor</div>', unsafe_allow_html=True)
st.write("This app extracts real mailing addresses from websites using GPT-4o. It scans the homepage and related contact/location pages with smart chunking.")

# 🔍 GPT function with chunk merge
def gpt_extract_chunked_text(chunks, thread_id):
    all_addresses = []
    client = get_client(thread_id)

    for chunk in chunks:
        prompt = f"""
You are a strict mailing address extractor.

Extract only real, physical addresses from the text below. Format the output as a clean Python list of lists:
[["Street", "City", "State", "ZIP"], ...]

No phone numbers, names, or guesses. If nothing, return [].

Text:
{chunk}
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            raw_output = response.choices[0].message.content.strip()
            extracted = ast.literal_eval(raw_output)

            if isinstance(extracted, list):
                all_addresses.extend(extracted)
        except:
            continue

    if all_addresses:
        seen = set()
        cleaned = []
        for parts in all_addresses:
            flat = ", ".join(p.strip() for p in parts)
            if flat not in seen:
                seen.add(flat)
                cleaned.append(flat)
        return " | ".join(cleaned)
    return ""

# 🌐 Scrape and read page
def fetch_page_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            return soup.get_text(separator=" ", strip=True)
    except:
        return ""
    return ""

# 🔗 Find contact/location subpages
def find_subpages(baseUrl, html):
    soup = BeautifulSoup(html, "html.parser")
    pages = set()
    keywords = ["contact", "location", "find-us", "get-in-touch"]

    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        if any(k in href for k in keywords):
            full = urljoin(baseUrl, href)
            pages.add(full)
    return list(pages)

# 🧠 Main processor per URL
def process_url_full(url, thread_id):
    if not isinstance(url, str) or not url.strip():
        return ""

    if not url.startswith("http"):
        url = "https://" + url.strip()

    all_text = []

    main_text = fetch_page_text(url)
    if main_text:
        all_text.append(main_text)

    sub_links = find_subpages(url, main_text)
    for sub in sub_links:
        sub_text = fetch_page_text(sub)
        if sub_text:
            all_text.append(sub_text)

    combined = " ".join(all_text).strip()
    chunks = [combined[i:i + 12000] for i in range(0, len(combined), 12000)]
    return gpt_extract_chunked_text(chunks, thread_id)

# ✅ Multithreaded batch
def process_all(df, max_workers=10):
    urls = df["URL"].tolist()
    results = [None] * len(urls)
    failed = []

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_url_full, url, i): i for i, url in enumerate(urls)}
        progressBar = st.progress(0)
        total = len(futures)

        for idx, future in enumerate(as_completed(futures)):
            i = futures[future]
            try:
                result = future.result()
                results[i] = result if result.strip() else "Unknown"
                if result.strip() == "":
                    failed.append(urls[i])
            except:
                results[i] = "Unknown"
                failed.append(urls[i])

            elapsed = time.time() - start_time
            avg_per_url = elapsed / (idx + 1)
            remaining = avg_per_url * (total - (idx + 1))
            progressBar.progress((idx + 1) / total)
            st.caption(f"⏳ Estimated time left: {int(remaining)} sec")

    df["Extracted Addresses"] = results
    return df, failed

# 📤 Upload UI
st.markdown('<div class="section-header">📁 Upload Excel File</div>', unsafe_allow_html=True)
uploadedFile = st.file_uploader("Upload your .xlsx file with a 'URL' column", type=["xlsx"])

if uploadedFile:
    try:
        df = pd.read_excel(uploadedFile)
        if "URL" not in df.columns:
            st.error("❌ Excel must contain a column named 'URL'.")
        else:
            st.success("✅ File uploaded successfully.")

            st.markdown('<div class="section-header">🔍 Extracting Addresses...</div>', unsafe_allow_html=True)
            with st.spinner("Scanning websites using GPT-4o..."):
                result_df, failed_urls = process_all(df)

            st.success("✅ Extraction complete!")
            st.dataframe(result_df, use_container_width=True)

            output = BytesIO()
            result_df.to_excel(output, index=False)
            st.download_button(
                label="⬇️ Download Results",
                data=output.getvalue(),
                file_name="gpt4o_extracted_addresses.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.markdown('<div class="section-header">⚠️ Sites With No Address Found</div>', unsafe_allow_html=True)
            st.markdown(f"**{len(failed_urls)}** out of **{len(df)}** sites had no address.")
            if failed_urls:
                st.dataframe(pd.DataFrame({"Check Manually": failed_urls}))

    except Exception as e:
        st.error(f"❌ Failed to process file: {str(e)}")
