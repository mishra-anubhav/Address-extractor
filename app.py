import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from io import BytesIO

st.set_page_config(page_title="📬 Smart Address Extractor", layout="centered")
st.title("📬 Website Address Extractor with Contact + Location Logic")
st.write("Upload an Excel file with a column named **URL**. This app will extract all address info from the site’s main page, contact pages, and location pages.")

# Extract all address-like data from <address> or regex
def extract_addresses_from_html(htmlContent):
    soup = BeautifulSoup(htmlContent, "html.parser")
    addresses = set()

    # Step 1: Collect from <address> tag (best-case)
    for tag in soup.find_all("address"):
        text = tag.get_text(separator=" ", strip=True)
        if text:
            addresses.add(text)

    # Step 2: Heuristic search in <div>, <p>, <li>, <span> with context
    candidateTags = soup.find_all(["div", "p", "li", "span"])
    keywords = ["address", "location", "clinic", "directions", "find us", "visit us", "headquarters"]

    for tag in candidateTags:
        text = tag.get_text(separator=" ", strip=True)
        textLower = text.lower()

        # Skip super short or unrelated content
        if len(text) < 20:
            continue

        # Check keyword presence or address-like structure
        if any(keyword in textLower for keyword in keywords) or re.search(r"\d{1,5} [\w\s.,-]{10,}", text):
            # Check if it looks like part of a US address (relaxed)
            if re.search(r"[A-Z]{2} \d{5}", text) or re.search(r"\d{5}", text):
                addresses.add(text)

    # Step 3: Regex fallback on raw text for isolated address strings
    plainText = soup.get_text(separator=" ", strip=True)
    matches = re.findall(r"\d{1,5}[\w\s\.,-]{5,40}(?:[A-Z]{2}\s?\d{5})", plainText)
    for match in matches:
        addresses.add(match.strip())

    return list(addresses)


# Find all contact/location-like pages
def find_related_pages(baseUrl, htmlContent):
    soup = BeautifulSoup(htmlContent, "html.parser")
    relatedUrls = []
    keywords = ["contact", "contact-us", "get-in-touch", "support", "location", "locations", "find-us", "our-offices"]

    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        text = link.get_text().lower()
        if any(keyword in href or keyword in text for keyword in keywords):
            # Normalize to full URL
            if href.startswith("http"):
                relatedUrls.append(href)
            elif href.startswith("/"):
                relatedUrls.append(baseUrl.rstrip("/") + href)

    return list(set(relatedUrls))

# Main address processor with fallback and progress bar
def process_links(df):
    results = []
    progress = st.progress(0)
    total = len(df)

    for i, url in enumerate(df['URL']):
        extractedAddresses = []

        try:
            if not isinstance(url, str) or url.strip() == "":
                results.append("Invalid URL")
                progress.progress((i + 1) / total)
                continue

            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url.strip()

            headers = {"User-Agent": "Mozilla/5.0"}

            # Load main page
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                extractedAddresses.extend(extract_addresses_from_html(res.text))
                relatedUrls = find_related_pages(url, res.text)

                for relatedUrl in relatedUrls:
                    try:
                        sub = requests.get(relatedUrl, headers=headers, timeout=10)
                        if sub.status_code == 200:
                            extractedAddresses.extend(extract_addresses_from_html(sub.text))
                    except Exception as e:
                        continue
            else:
                results.append(f"Failed: {res.status_code}")
                progress.progress((i + 1) / total)
                continue

        except Exception as e:
            results.append(f"Error: {str(e)}")
            progress.progress((i + 1) / total)
            continue

        # Final formatting
        final = list(set(extractedAddresses))
        if final:
            results.append(" | ".join(final))
        else:
            st.warning(f"⚠️ No address found for: {url}")
            results.append("No address found")

        progress.progress((i + 1) / total)

    df['Extracted Addresses'] = results
    return df


# Upload section
uploadedFile = st.file_uploader("📤 Upload Excel File (.xlsx)", type=["xlsx"])

if uploadedFile:
    try:
        df = pd.read_excel(uploadedFile)
        st.write("✅ Columns found:", df.columns.tolist())

        if "URL" not in df.columns:
            st.error("❌ Excel must contain a column named 'URL'.")
        else:
            with st.spinner("Scraping all pages..."):
                result_df = process_links(df)

            st.success("🎉 Scraping complete!")
            st.dataframe(result_df)

            output = BytesIO()
            result_df.to_excel(output, index=False)
            st.download_button(
                label="⬇️ Download Output Excel",
                data=output.getvalue(),
                file_name="output_links_with_addresses.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"❌ Failed to read file: {str(e)}")
