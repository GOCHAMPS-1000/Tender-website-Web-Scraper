import time
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup, Tag
from playwright.sync_api import sync_playwright, Page, Browser
import re
from typing import Union, Tuple
from deep_translator import GoogleTranslator

# --- Configuration ---
SEARCH_URL = "https://ted.europa.eu/en/search/result?FT=Adalimumab&search-scope=ACTIVE&scope=ACTIVE&onlyLatestVersions=false&facet.publication-date=2024&sortColumn=publication-number&sortOrder=DESC&page=1&simpleSearchRef=true"
SEARCH_WAIT_ELEMENT = "app-notice-summary"
DETAIL_WAIT_ELEMENT = "app-notice-detail"
OUTPUT_CSV_PATH = "adalimumab_tenders.csv"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"

# --- Translation Helper Function ---
def translate_text(text_to_translate: str) -> str:
    """Translates text to English. Returns original text on failure."""
    if not text_to_translate or text_to_translate == "N/A" or not isinstance(text_to_translate, str):
        return text_to_translate
    
    # Basic check for already English text (simplistic)
    if all(ord(c) < 128 for c in text_to_translate):
         return text_to_translate

    try:
        translated_text = GoogleTranslator(source='auto', target='en').translate(text_to_translate)
        return translated_text if translated_text else text_to_translate
    except Exception as e:
        #print(f"Translation failed for '{text_to_translate[:50]}...': {e}")
        return text_to_translate # Return original on error

# --- Helper Function from Step (2) ---
def extract_notice_data(row: Tag) -> Union[dict, None]:
    """Extracts data from a search result row."""
    data = {
        "Notice Number": "N/A",
        "Description": "N/A",
        "Country": "N/A",
        "Publication Date": "N/A",
        "Deadline": "N/A"
    } 

    cells = row.find_all('td', recursive=False)
    if len(cells) < 6:
        return None

    notice_link = cells[1].find('a', class_='css-q5fadx')
    if notice_link:
        data["Notice Number"] = notice_link.get_text(strip=True)

    desc_list = cells[2].find('ul')
    if desc_list:
        first_desc_item = desc_list.find('li', class_='css-1evkt30')
        if first_desc_item:
            desc_parts = [part.get_text(strip=True) for part in first_desc_item.find_all(['span'], recursive=False)]
            description = "".join(desc_parts)
            data["Description"] = translate_text(description)

    data["Country"] = cells[3].get_text(strip=True)

    pub_date_list = cells[4].find('ul')
    if pub_date_list:
        first_pub_date_item = pub_date_list.find('li', class_='css-v9egcd')
        if first_pub_date_item:
            data["Publication Date"] = first_pub_date_item.get_text(strip=True)

    deadline_cell = cells[5]
    deadline_list = deadline_cell.find('ul')
    if deadline_list:
        deadlines = [li.get_text(strip=True) for li in deadline_list.find_all('li', class_='css-v9egcd')]
        data["Deadline"] = " / ".join(deadlines)
    else:
        deadline_span = deadline_cell.find('span', class_='css-v9egcd')
        if deadline_span:
            data["Deadline"] = deadline_span.get_text(strip=True)

    if data["Notice Number"] == "N/A" and data["Description"] == "N/A":
        return None

    return data


# --- Helper Functions from Step (4) ---
def get_data_text(element: Tag) -> str:
    """Safely gets text from a BeautifulSoup element."""
    if not element:
        return "N/A"
    link = element.find('a')
    if link:
        return link.get_text(strip=True)
    return element.get_text(strip=True)

def find_label_sibling_data(soup_element: Tag, label_text: str) -> str:
    """Finds a label span containing label_text and returns the text of the next sibling span (data)."""
    if not soup_element:
        return "N/A"
    label_span = soup_element.find('span', class_='label', string=lambda text: text and label_text in text)
    if label_span:
        data_span = label_span.find_next_sibling('span', class_='data')
        if data_span:
             return get_data_text(data_span)
        next_sibling = label_span.next_sibling
        if next_sibling and isinstance(next_sibling, str) and next_sibling.strip():
            return next_sibling.strip()
        sibling_div = label_span.find_next_sibling('div')
        if sibling_div:
             return sibling_div.get_text(strip=True, separator=', ')
    return "N/A"

def find_section_div(soup: BeautifulSoup, data_label_key: str) -> Union[Tag, None]:
    """Finds the main div for a section using its data-labels-key."""
    section_span = soup.find('span', {'data-labels-key': data_label_key})
    if section_span:
        return section_span.find_parent('div', id=re.compile(r'^section.*'))
    return None

def find_first_lot_section(soup: BeautifulSoup) -> Union[Tag, None]:
    """ Finds the first LOT section div based on typical starting IDs or labels """
    lot_span = soup.find('span', {'data-labels-key': 'auxiliary|text|lot'})
    if lot_span:
        lot_section = lot_span.find_parent('div', id=re.compile(r'^section.*'))
        if lot_section:
            return lot_section
    return soup.find('div', id=re.compile(r'^(section5_|sectionV_)'))


def convert_currency(amount_str: str, from_currency: str, to_currency: str = "INR") -> Tuple[str, float]:
    """Converts currency using a free API."""
    if not isinstance(amount_str, str): amount_str = str(amount_str)
    if not isinstance(from_currency, str): from_currency = "N/A"

    try:
        cleaned_amount_str = re.sub(r'[^\d,.]', '', amount_str)
        if ',' in cleaned_amount_str and '.' in cleaned_amount_str:
            if cleaned_amount_str.rfind('.') < cleaned_amount_str.rfind(','):
                 cleaned_amount_str = cleaned_amount_str.replace('.', '')
                 cleaned_amount_str = cleaned_amount_str.replace(',', '.')
            else:
                 cleaned_amount_str = cleaned_amount_str.replace(',', '')
        elif ',' in cleaned_amount_str:
             cleaned_amount_str = cleaned_amount_str.replace(',', '.')

        amount = float(cleaned_amount_str)
    except (ValueError, AttributeError):
        return f"N/A (Invalid amount: {amount_str})", 0.0

    if from_currency == "N/A" or amount == 0.0:
        return "N/A (No currency or amount)", 0.0
        
    if from_currency == to_currency:
        return f"{amount:,.2f} {to_currency}", amount

    try:
        api_url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        rate = data.get("rates", {}).get(to_currency)

        if not rate:
            return f"N/A (Could not find rate for {to_currency})", amount

        converted_amount = amount * rate
        return f"{converted_amount:,.2f} {to_currency}", converted_amount

    except requests.exceptions.RequestException as e:
        print(f"Currency conversion API failed for {from_currency}: {e}")
        return f"N/A (API error)", amount
    except Exception as e:
        print(f"Currency conversion failed for {amount_str} {from_currency}: {e}")
        return "N/A (Conversion error)", amount


# --- Updated Helper to Parse Detail Page (More Robust, conclusion_date removed) ---
def scrape_notice_detail(html_content: str, notice_id: str) -> dict:
    """
    Parses the HTML of a single notice detail page using robust selectors.
    Removed conclusion_date field.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # REMOVED conclusion_date
        extracted_data = {
            "buyer_name": "N/A",
            "buyer_email": "N/A",
            "value_original": "N/A",
            "currency_original": "N/A",
            "value_inr": "N/A",
            "start_date": "N/A",
            "end_date": "N/A",
            # "conclusion_date": "N/A", # Removed
            "pdf_link": "N/A",
            "organisations": "[]", 
            "tender_id": "N/A"
        }

        # --- Use Summary Section if available ---
        summary_section = soup.find('section', id='summary')
        if summary_section:
            buyer_summary_div = summary_section.find('div', class_='summary-section')
            if buyer_summary_div:
                 buyer_name_raw = find_label_sibling_data(buyer_summary_div, "Buyer")
                 if buyer_name_raw != 'N/A':
                     extracted_data["buyer_name"] = translate_text(buyer_name_raw)
                 email_raw = find_label_sibling_data(buyer_summary_div, "Email")
                 if email_raw != 'N/A':
                     extracted_data["buyer_email"] = email_raw

            value_label = summary_section.find('span', class_='label', string=lambda t: t and ('Estimated value' in t or 'Total value' in t))
            if value_label and value_label.parent:
                data_spans = value_label.parent.find_all('span', class_='data')
                if len(data_spans) >= 2:
                    extracted_data["value_original"] = get_data_text(data_spans[0])
                    extracted_data["currency_original"] = get_data_text(data_spans[1])

            lot_summary_header = summary_section.find('span', class_='bold', string=re.compile(r'^LOT-\d+'))
            if lot_summary_header:
                 lot_summary_section = lot_summary_header.find_parent('div')
                 if lot_summary_section:
                      date_section = lot_summary_section.find_next_sibling('div', class_='summary-section')
                      if date_section:
                           start_date_raw = find_label_sibling_data(date_section, 'Start date')
                           if start_date_raw != 'N/A': extracted_data["start_date"] = start_date_raw
                           end_date_raw = find_label_sibling_data(date_section, 'Duration end date')
                           if end_date_raw != 'N/A': extracted_data["end_date"] = end_date_raw

        # --- Fallback/Detailed Section Scraping ---
        if extracted_data["buyer_name"] == "N/A":
            buyer_section = find_section_div(soup, 'auxiliary|text|buyer') or find_section_div(soup, 'Part I: Contracting authority') 
            if buyer_section:
                 first_org_content = buyer_section.find_next_sibling('div', class_='section-content')
                 if first_org_content and first_org_content.find('span', class_='bold', string=re.compile(r'^ORG-')):
                     buyer_name_raw = find_label_sibling_data(first_org_content, "Official name")
                     if buyer_name_raw != 'N/A': extracted_data["buyer_name"] = translate_text(buyer_name_raw)
                     email_raw = find_label_sibling_data(first_org_content, "Email")
                     if email_raw != 'N/A': extracted_data["buyer_email"] = email_raw

        if extracted_data["value_original"] == "N/A":
            procedure_section = find_section_div(soup, 'auxiliary|text|procedure') or find_section_div(soup, 'Part II: Object')
            if procedure_section:
                 value_label = procedure_section.find('span', class_='label', string=lambda t: t and ('Estimated total value' in t or 'Total value' in t))
                 if value_label and value_label.parent:
                      data_spans = value_label.parent.find_all('span', class_='data')
                      if len(data_spans) >= 2:
                           extracted_data["value_original"] = get_data_text(data_spans[0])
                           extracted_data["currency_original"] = get_data_text(data_spans[1])

        if extracted_data["value_original"] != "N/A":
            inr_string, _ = convert_currency(extracted_data["value_original"], extracted_data["currency_original"])
            extracted_data["value_inr"] = inr_string

        if extracted_data["start_date"] == "N/A": # Only check if not found in summary
            procedure_section = find_section_div(soup, 'auxiliary|text|procedure') or find_section_div(soup, 'Part II: Object')
            if procedure_section:
                 date_label = procedure_section.find('span', class_='label', string=lambda t: t and ('Start date' in t or 'Duration' in t))
                 if date_label:
                      date_container = date_label.find_parent('div', class_=lambda x: x != 'section-content') 
                      if date_container:
                            start_date_raw = find_label_sibling_data(date_container, 'Start date')
                            if start_date_raw != 'N/A': extracted_data["start_date"] = start_date_raw
                            end_date_raw = find_label_sibling_data(date_container, 'End date') # Try finding 'End date' as well
                            if end_date_raw != 'N/A': extracted_data["end_date"] = end_date_raw

            # REMOVED: Section looking for conclusion_date

        formats_section = soup.find('div', id='formats-accordion')
        if formats_section:
            pdf_header = formats_section.find('h4', string='PDF')
            if pdf_header:
                pdf_container = pdf_header.find_parent('div', class_='css-188ozac')
                if pdf_container:
                    pdf_link_tag = pdf_container.find('a', id='EN', class_='download-pdf')
                    if pdf_link_tag and pdf_link_tag.has_attr('href'):
                        extracted_data["pdf_link"] = pdf_link_tag['href']

        org_list = []
        org_sections = soup.find_all('div', class_='section-content')
        for section in org_sections:
            org_id_tag = section.find('span', class_='bold', string=lambda t: t and t.startswith('ORG-'))
            if not org_id_tag:
                 continue

            org_id = get_data_text(org_id_tag)
            org_name_original = find_label_sibling_data(section, "Official name")
            org_name = translate_text(org_name_original)
            reg_num = find_label_sibling_data(section, "Registration number")
            
            roles_list = []
            roles_header = section.find('span', class_='bold', string=lambda t: t and 'Roles of this organisation' in t)
            roles_container = None
            if roles_header:
                roles_container = roles_header.find_parent('div')
                if not roles_container or not roles_container.find('span', class_='label'):
                     potential_sibling = roles_header.find_next_sibling('div')
                     if potential_sibling and potential_sibling.find('span', class_='label'):
                          roles_container = potential_sibling

            if roles_container:
                for role_label in roles_container.find_all('span', class_='label'):
                    roles_list.append(role_label.get_text(strip=True))

            if org_name != "N/A":
                org_list.append({
                    "Org ID": org_id,
                    "Official Name": org_name,
                    "Registration Number": reg_num,
                    "Roles": list(set(roles_list)) 
                })
        
        extracted_data["organisations"] = json.dumps(org_list)

        notice_info_section_div = find_section_div(soup, 'auxiliary|text|notice-information')
        if notice_info_section_div:
            notice_info_content = notice_info_section_div.find_next_sibling('div', class_='section-content')
            if notice_info_content:
                id_label = notice_info_content.find('span', class_='label', string=lambda t: t and 'Notice identifier/version' in t)
                if id_label and id_label.parent:
                    id_spans = id_label.parent.find_all('span', class_='data')
                    if len(id_spans) >= 1:
                         part1 = get_data_text(id_spans[0])
                         part2 = get_data_text(id_spans[1]) if len(id_spans) >= 2 else ""
                         tender_id_text = f"{part1} - {part2}".strip(' -')
                         extracted_data["tender_id"] = translate_text(tender_id_text)

        return extracted_data

    except Exception as e:
        print(f"CRITICAL Error parsing detail page for {notice_id}: {e}")
        return {"Notice Number": notice_id, "error": f"Parsing failed: {e}"}


# --- Main Unified Scraper Function ---
def main():
    """Main function to run the unified scraper."""
    all_tender_data = []
    
    print("--- Starting Method 1: IN-MEMORY Scraper (with Translation + Robust Selectors, no conclusion date) ---")
    
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(headless=False) 
            page = browser.new_page(user_agent=USER_AGENT)
            page.set_viewport_size({"width": 1920, "height": 1080})

            # STEP 1: Get Search Results Page
            print(f"Navigating to search URL...") 
            print(SEARCH_URL) 
            page.goto(SEARCH_URL, wait_until='networkidle', timeout=60000) 

            print(f"Waiting for element '{SEARCH_WAIT_ELEMENT}' to load...") 
            try:
                page.wait_for_selector(SEARCH_WAIT_ELEMENT, timeout=60000) 
                time.sleep(3) 
                print("Search page dynamic content loaded.") 
            except Exception as e:
                print(f"Warning: Search page timed out or element '{SEARCH_WAIT_ELEMENT}' not found. Continuing with potentially partial HTML.")
                print(f"Error details: {e}")
            
            search_html_content = page.content() 

            # STEP 2: Parse Search Results
            print("Parsing search results...")
            soup_search = BeautifulSoup(search_html_content, 'html.parser') 
            table_body = soup_search.find('tbody', class_='CustomReactClasses-MuiTableBody-root')
            
            if not table_body:
                print("Could not find results table body (tbody) in the search page HTML.")
                print("The page may be incomplete, blocked, or the structure changed. Exiting.")
                if browser: browser.close()
                return

            rows = table_body.find_all('tr', class_='CustomReactClasses-MuiTableRow-root', recursive=False)
            print(f"Found {len(rows)} potential notices on the page.")

            basic_notice_list = []
            for row in rows:
                notice_info = extract_notice_data(row)
                if notice_info and notice_info.get("Notice Number") != "N/A":
                    basic_notice_list.append(notice_info)
            
            if not basic_notice_list:
                 print("Extracted 0 valid notices from search results. Exiting.")
                 if browser: browser.close()
                 return
                 
            print(f"Extracted {len(basic_notice_list)} valid notices. Now scraping details...")

            # STEPS 3 & 4: Loop, Get, and Parse Detail Pages
            for i, basic_info in enumerate(basic_notice_list, 1):
                notice_id = basic_info["Notice Number"]
                if not notice_id or not re.match(r'^\d+-\d+$', notice_id):
                    print(f"Skipping invalid notice_id format: {notice_id}")
                    all_tender_data.append({**basic_info, "error": "Invalid Notice Number format"})
                    continue

                detail_url = f"https://ted.europa.eu/en/notice/-/detail/{notice_id}" 
                
                print(f"\n--- Scraping detail {i}/{len(basic_notice_list)}: {notice_id} ---")
                
                detail_html_content = "" 
                try: 
                    print(f"Navigating to {detail_url}")
                    page.goto(detail_url, wait_until='domcontentloaded', timeout=60000) 
                    
                    print(f"Waiting for detail element '{DETAIL_WAIT_ELEMENT}'...")
                    try:
                        page.wait_for_selector(DETAIL_WAIT_ELEMENT, timeout=30000) 
                        print("Detail page dynamic content potentially loaded.")
                        time.sleep(3) 
                    except Exception as e_detail:
                        print(f"Warning: Detail page timed out or element '{DETAIL_WAIT_ELEMENT}' not found for {notice_id}.")
                        print(f"Error details: {e_detail}")
                        print("Proceeding to get content anyway.")
                    
                    detail_html_content = page.content() 
                    
                    if not detail_html_content:
                         print(f"Failed to retrieve HTML content for {notice_id}. Skipping parsing.")
                         raise ValueError("Empty HTML content retrieved.")

                    detail_info = scrape_notice_detail(detail_html_content, notice_id)
                    
                    combined_data = {**basic_info, **detail_info}
                    all_tender_data.append(combined_data)
                    print(f"Successfully processed {notice_id}.")

                except Exception as e_loop:
                    print(f"A fatal error occurred processing {notice_id}: {e_loop}")
                    if "error" not in basic_info: 
                         basic_info["error"] = f"Failed to scrape or parse detail page: {e_loop}"
                    all_tender_data.append(basic_info) 


            browser.close()
            print("\n--- Browser closed ---")

        except Exception as e_outer:
            print(f"An unexpected fatal error occurred in the main process: {e_outer}") 
            if browser and browser.is_connected():
                browser.close()

    # --- FINAL STEP: Save to single CSV ---
    if not all_tender_data:
        print("\nNo valid data was successfully processed or saved.")
        return

    print(f"\nScraping complete. Saving {len(all_tender_data)} records to CSV...")
    try:
        df = pd.DataFrame(all_tender_data)
        
        cols_order = [
            "Notice Number", "Description", "Country", "Publication Date", "Deadline",
            "buyer_name", "buyer_email", "tender_id", "organisations", 
            "value_original", "currency_original", "value_inr",
            "start_date", "end_date", "pdf_link", "error" 
        ]
        
        actual_cols = df.columns.tolist()
        final_cols_order = [col for col in cols_order if col in actual_cols]
        extra_cols = [col for col in actual_cols if col not in final_cols_order]
        final_cols_order.extend(extra_cols)
        
        df = df[final_cols_order]

        df.to_csv(OUTPUT_CSV_PATH, index=False, encoding='utf-8-sig')
        print(f"\nSuccessfully saved data to '{OUTPUT_CSV_PATH}'")
        
        success_count = sum(1 for item in all_tender_data if 'error' not in item or item.get('error') is None)
        fail_count = len(all_tender_data) - success_count
        print(f"Summary: {success_count} notices processed successfully, {fail_count} encountered errors.")

    except Exception as e:
        print(f"An error occurred while saving the final CSV file: {e}")

if __name__ == "__main__":
    main()