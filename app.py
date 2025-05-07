import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from io import BytesIO

# Streamlit page setup
st.set_page_config(page_title="📬 Address Extractor", layout="centered")
st.title("📬 Website Address Extractor with Smart Fallback")
st.write("Upload an Excel file with a 'URL' column. This app fetches each site and extracts address info from the main or 'Contact Us' page.")

# 📍 Function to extract address from HTML
def extract_address_from_html(htmlContent):
    soup = BeautifulSoup(htmlContent, "html.parser")

    # Check <address> tag
    addressTag = soup.find("address")
    if addressTag:
        return addressTag.get_text(strip=True)

    # Regex for US-style addresses
    regexPattern = r"\d{1,5}\s[\w\s]{2,40},?\s[\w\s]{2,40},?\s[A-Z]{2}\s\d{5}"
    match = re.search(regexPattern, soup.get_text())
    if match:
        return match.group(0)

    return "Address Not Found"

# 🔍 Look for contact link in page
def find_contact_page_url(baseUrl, htmlContent):
    soup = BeautifulSoup(htmlContent, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        if "contact" in href:
            # Convert to full URL if relative
            if href.startswith("http"):
                return href
            elif href.startswith("/"):
                return baseUrl.rstrip("/") + href
    return None

# 📤 Main scraping function with progress bar
def process_links(df):
    addresses = []
    progress = st.progress(0)
    total = len(df)

    for i, url in enumerate(df['URL']):
        if not isinstance(url, str) or url.strip() == "":
            addresses.append("Invalid URL")
            progress.progress((i + 1) / total)
            continue

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url.strip()

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                addresses.append(f"Failed: {response.status_code}")
                progress.progress((i + 1) / total)
                continue

            # Try address from main page
            address = extract_address_from_html(response.text)

            if address == "Address Not Found":
                # Try 'Contact' page
                contactUrl = find_contact_page_url(url, response.text)
                if contactUrl:
                    contactResp = requests.get(contactUrl, headers=headers, timeout=10)
                    if contactResp.status_code == 200:
                        address = extract_address_from_html(contactResp.text)
                    else:
                        address = f"Failed: {contactResp.status_code} (contact)"
                else:
                    address = "Contact page not found"

        except Exception as e:
            address = f"Error: {str(e)}"

        addresses.append(address)
        progress.progress((i + 1) / total)

    df['Extracted Address'] = addresses
    return df

# 📥 Upload Excel
uploadedFile = st.file_uploader("Upload Excel File (.xlsx)", type=["xlsx"])

if uploadedFile:
    df = pd.read_excel(uploadedFile)

    if "URL" not in df.columns:
        st.error("❌ Excel must contain a column named 'URL'.")
    else:
        with st.spinner("🔍 Scraping websites..."):
            result_df = process_links(df)

        st.success("✅ Scraping Complete!")
        st.dataframe(result_df)

        output = BytesIO()
        result_df.to_excel(output, index=False)
        st.download_button(
            label="⬇️ Download Results as Excel",
            data=output.getvalue(),
            file_name="output_links_with_addresses.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
