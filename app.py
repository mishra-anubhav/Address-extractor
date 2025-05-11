import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from urllib.parse import urljoin, urlparse
from openai import OpenAI

# ---- CONFIG ----
client = OpenAI(api_key=st.secrets["openai_api_key"])
st.set_page_config(
    page_title="AI-Powered Address Finder",
    page_icon="📍",
    layout="centered"
)

# ---- MODERN STYLING ----
st.markdown("""
<style>
/* Background gradient white → gray */
html, body, [class*="css"]  {
    font-family: 'Helvetica Neue', sans-serif;
    background: linear-gradient(to bottom, #ffffff, #f2f2f5);
    color: #111;
}

/* Headline */
h1 {
    text-align: center;
    font-weight: 700;
    font-size: 3em;
    color: #111;
    margin-top: 0.5em;
    margin-bottom: 0.25em;
}

/* Description */
.description {
    text-align: left;
    font-size: 1.1em;
    color: #555;
    margin-bottom: 2em;
}

/* Buttons */
button[kind="primary"] {
    background-color: #4f46e5;
    color: white;
    border-radius: 8px;
    padding: 0.6em 1.2em;
    font-size: 1em;
}
.stDownloadButton {
    margin-top: 1em;
}
</style>
""", unsafe_allow_html=True)


# ---- HEADER ----
st.markdown("### 📍 AI-Powered Address Finder")
st.markdown(
    '<div class="description">Upload a list of URLs, and let our GPT-4o assistant extract accurate U.S. mailing addresses for you — fast, clean, and reliable.</div>',
    unsafe_allow_html=True
)

# ---- CORE LOGIC ----
def fetch_page_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            return soup.get_text(separator=" ", strip=True), res.text
    except:
        return "", ""
    return "", ""

def find_subpages(base_url, html):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(x in href for x in ["contact", "location", "get-in-touch", "directions"]):
            links.add(urljoin(base_url, href))
    return list(links)

def query_gpt_with_text(text):
    prompt = f"""
You are a reliable assistant for extracting real-world physical mailing addresses.

Return only physical mailing addresses in U.S. format as a Python list of lists like:
[["123 Main St", "Dallas", "TX", "75201"], ["456 Center Blvd", "San Jose", "CA", "95110"]]

Do not include phone numbers, emails, names, or anything else.

Here is the extracted page content:
{text}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ GPT Error: {e}"

def process_url(url):
    allTextChunksFromMainAndSubpages = []

    mainPageText, mainPageHTML = fetch_page_text(url)
    allTextChunksFromMainAndSubpages.append(mainPageText)

    subpagesList = find_subpages(url, mainPageHTML)
    for subpage in subpagesList:
        subPageText, _ = fetch_page_text(subpage)
        allTextChunksFromMainAndSubpages.append(subPageText)

    combinedText = " ".join(allTextChunksFromMainAndSubpages).strip()
    if not combinedText:
        return "", "❌ No text found."

    combinedText = combinedText[:12000]
    gptResponseRaw = query_gpt_with_text(combinedText)

    # Clean markdown formatting from GPT
    for prefix in ["```python", "```json", "```"]:
        if gptResponseRaw.startswith(prefix):
            gptResponseRaw = gptResponseRaw[len(prefix):].strip()
    if gptResponseRaw.endswith("```"):
        gptResponseRaw = gptResponseRaw[:-3].strip()

    return combinedText, gptResponseRaw

def process_all(df):
    urls = df["URL"].astype(str).fillna("").str.strip()
    successRows = []
    failedRows = []

    progressBar = st.progress(0)
    progressText = st.empty()
    totalUrls = len(urls)

    for index, url in enumerate(urls):
        originalUrl = url
        if not url or url.lower() == "nan":
            failedRows.append({"URL": originalUrl, "Error": "Invalid URL"})
            continue

        if not url.startswith("http"):
            url = "https://" + url

        domainName = urlparse(url).netloc
        progressText.markdown(f"🔄 Processing: `{domainName}`")

        try:
            combinedText, gptOutput = process_url(url)
            if gptOutput.strip().startswith("❌ No text found."):
                failedRows.append({"URL": originalUrl, "Error": "❌ No text found."})
                progressText.markdown(f"❌ No text: `{domainName}`")
            else:
                successRows.append({"URL": originalUrl, "Extracted Addresses": gptOutput})
                progressText.markdown(f"✅ Done: `{domainName}`")
        except Exception as e:
            failedRows.append({"URL": originalUrl, "Error": f"❌ Error: {e}"})
            progressText.markdown(f"❌ Failed: `{domainName}`")

        progressBar.progress((index + 1) / totalUrls)

    # Success output
    if successRows:
        successDf = pd.DataFrame(successRows)
        st.success("🎉 Processed successfully.")
        st.dataframe(successDf)

        successBuffer = BytesIO()
        successDf.to_excel(successBuffer, index=False)
        st.download_button(
            label="⬇️ Download Excel with Extracted Addresses",
            data=successBuffer.getvalue(),
            file_name="gpt_addresses_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # Failed output
    if failedRows:
        failedDf = pd.DataFrame(failedRows)
        st.warning("⚠️ Some URLs failed to process.")
        st.dataframe(failedDf)

        failedBuffer = BytesIO()
        failedDf.to_excel(failedBuffer, index=False)
        st.download_button(
            label="⬇️ Download Excel with Failed URLs",
            data=failedBuffer.getvalue(),
            file_name="gpt_failed_urls.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ---- FILE UPLOAD ----
uploaded_file = st.file_uploader("📤 Upload Excel File (.xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        st.success("✅ File uploaded.")

        if "URL" not in df.columns:
            st.error("❌ Excel must contain a column named `URL`.")
        else:
            st.info("⏳ Running GPT extraction. Please wait...")
            process_all(df)
    except Exception as e:
        st.error(f"❌ Error reading file: {str(e)}")

# ---- FOOTER ----
st.markdown("""<hr style="margin-top:2em; margin-bottom:1em;">""", unsafe_allow_html=True)
st.markdown(
    '<div style="text-align:center; font-size:0.9em; color:#888;">Made with ❤️ by Anubhav</div>',
    unsafe_allow_html=True
)
