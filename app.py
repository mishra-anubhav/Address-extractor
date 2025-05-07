import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from io import BytesIO

st.set_page_config(page_title="Link Address Scraper", layout="centered")

st.title("Website Address Extractor")
st.write("Upload an Excel file with website links (in column A named 'URL'). This app extracts addresses from each link.")

def extract_address_from_html(htmlContent):
    soup = BeautifulSoup(htmlContent, "html.parser")
    addressTag = soup.find("address")
    if addressTag:
        return addressTag.get_text(strip=True)

    regexPattern = r"\d{1,5}\s[\w\s]{2,40},?\s[\w\s]{2,40},?\s[A-Z]{2}\s\d{5}"
    match = re.search(regexPattern, soup.get_text())
    if match:
        return match.group(0)

    return "Address Not Found"

def process_links(df):
    addresses = []
    for url in df['URL']:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                address = extract_address_from_html(response.text)
            else:
                address = f"Failed: {response.status_code}"
        except Exception as e:
            address = f"Error: {str(e)}"
        addresses.append(address)
    df['Extracted Address'] = addresses
    return df

uploadedFile = st.file_uploader("Upload Excel File (.xlsx)", type=["xlsx"])

if uploadedFile:
    df = pd.read_excel(uploadedFile)
    if "URL" not in df.columns:
        st.error("The Excel must contain a column named 'URL'.")
    else:
        with st.spinner("Scraping..."):
            result_df = process_links(df)
        st.success("Done!")

        st.dataframe(result_df)

        output = BytesIO()
        result_df.to_excel(output, index=False)
        st.download_button(
            label="Download Output Excel",
            data=output.getvalue(),
            file_name="output_links.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
