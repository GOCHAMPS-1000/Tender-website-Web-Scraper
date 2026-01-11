# Tender-website-Web-Scraper
This project is a specialized web scraping tool designed to extract European public procurement data related to Adalimumab for the year 2024. It navigates the TED (Tenders Electronic Daily) portal, identifies relevant notices, and performs a deep crawl to extract detailed contract information.

# TED Europa Adalimumab Tenders Scraper (2024)
This repository contains a robust Python-based web scraper designed to extract public procurement data from the **Tenders Electronic Daily (TED) Europa** portal. Specifically, it targets tenders related to **Adalimumab** published in the year **2024**.

The tool automates the process of searching, navigating to detailed notice pages, translating foreign language descriptions into English, and performing currency conversions to INR.

---

## Web Scraping

The project utilizes a multi-layered scraping strategy to handle modern web architectures:

* **Playwright (Headless Browser):** Used to render dynamic JavaScript content on the TED portal, ensuring that search results and notice details are fully loaded before extraction.
* **BeautifulSoup4:** Employed for surgical parsing of the HTML DOM to extract specific fields like buyer info, value, and organizational roles.
* **Deep Translator:** Integrates the `google-translator` to automatically detect and translate non-English descriptions and buyer names.
* **Currency Conversion:** Uses the `exchangerate-api` to convert estimated tender values from original currencies (EUR, PLN, etc.) to **INR**.

---

## Requirements

To run this scraper, you need **Python 3.8+** and the following dependencies:

* `playwright`: For browser automation.
* `beautifulsoup4`: For HTML parsing.
* `pandas`: For data structuring and CSV export.
* `requests`: For API calls (Currency conversion).
* `deep-translator`: For multilingual support.
* `lxml`: (Optional) Faster parsing backend for BeautifulSoup.

---

## Quick Setup

1. **Clone the Repository:**
```bash
git clone https://github.com/yourusername/adalimumab-tenders-scraper.git
cd adalimumab-tenders-scraper

```


2. **Install Dependencies:**
```bash
pip install playwright beautifulsoup4 pandas requests deep-translator

```


3. **Install Playwright Browsers:**
```bash
playwright install chromium

```


4. **Run the Scraper:**
```bash
python scraper_script.py

```



---

## Project Layout

```text
.
├── adalimumab_tenders.csv    # The final output (generated after run)
├── scraper_script.py         # Main execution script
├── README.md                 # Project documentation
└── .gitignore                # Folders to ignore (e.g., venv, __pycache__)

```

### Data Fields Extracted

| Field | Description |
| --- | --- |
| **Notice Number** | Unique TED identifier for the tender. |
| **Description** | Translated summary of the procurement. |
| **Value INR** | Estimated tender value converted to Indian Rupees. |
| **Buyer Name** | The contracting authority/organization. |
| **Organisations** | JSON string containing all involved ORGs and their roles. |
| **PDF Link** | Direct link to the official English notice PDF. |

---

## Notes

* **Rate Limiting:** The script includes `time.sleep(3)` pauses to respect the server's load and prevent IP blocking.
* **Translation:** Translation is performed on-the-fly. For large datasets, this may slightly increase execution time.
* **Currency API:** The currency conversion relies on a free tier API. If you encounter "API Error," verify your internet connection or check if the currency code is supported.
* **Headless Mode:** By default, `headless=False` is set in the script so you can watch the process. Change to `True` for faster, background execution.

---

## Licensing

This project is licensed under the **MIT License**. You are free to use, modify, and distribute this software for personal or commercial purposes. Please note that data extracted from TED Europa is subject to their own [Legal Notice](https://ted.europa.eu/en/legal-notice).

---
