import os
import sys
import requests
import pypandoc
from canvasapi import Canvas
from pathvalidate import sanitize_filename
from tqdm import tqdm
from weasyprint import HTML
from dotenv import load_dotenv

# CROSS-PLATFORM SYSTEM WRAPPER for Mac-Windows compatibility (I haven't tested Linux yet)
def setup_binary_paths():
    if sys.platform == 'darwin':
        hb_path = '/opt/homebrew/lib'
        if os.path.exists(hb_path):
            os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = hb_path + ":" + os.environ.get('DYLD_FALLBACK_LIBRARY_PATH', '')
            os.environ['G_MESSAGES_DEBUG'] = 'none'
    elif sys.platform == 'win32':
        gtk_path = r'C:\Program Files\GTK3-Runtime Win64\bin'
        if os.path.exists(gtk_path):
            os.add_dll_directory(gtk_path)
            
setup_binary_paths()
load_dotenv()

# --- CONFIGURATION ---
API_URL = os.getenv("CANVAS_API_URL", "https://dlsu.instructure.com")
API_KEY = os.getenv("API_KEY")
OUTPUT_DIR = "DLSU_Canvas_Archive"

# Print absolute path to help user find the data
ABS_OUTPUT_PATH = os.path.abspath(OUTPUT_DIR)

if not API_KEY:
    raise ValueError("FATAL: CANVAS_API_KEY not found. Check your .env file.")

def init_canvas():
    return Canvas(API_URL, API_KEY)

def download_file(url, filepath, file_size):
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f, tqdm(
            desc=os.path.basename(filepath),
            total=file_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
            leave=False
        ) as bar:
            for chunk in response.iter_content(chunk_size=8192):
                size = f.write(chunk)
                bar.update(size)
        return True
    except Exception as e:
        print(f"    [ERROR] Download failed: {e}")
        if os.path.exists(filepath): os.remove(filepath)
        return False

def save_page_as_pdf(page, output_path):
    try:
        if hasattr(page, 'body') and page.body:
            full_html = f"<html><head><meta charset='utf-8'></head><body><h1>{page.title}</h1>{page.body}</body></html>"
            HTML(string=full_html).write_pdf(output_path)
            print(f"    [SAVED] Page saved as PDF: {os.path.basename(output_path)}")
    except Exception as e:
        print(f"    [ERROR] WeasyPrint Failed: {e}")

def convert_docx_to_pdf(docx_path):
    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"
    try:
        pypandoc.convert_file(docx_path, 'pdf', outputfile=pdf_path, extra_args=['--pdf-engine=weasyprint'])
        print(f"    [CONVERTED] DOCX to PDF: {os.path.basename(pdf_path)}")
    except Exception as e:
        print(f"    [ERROR] DOCX to PDF conversion failed: {e}")

def main():
    print(f"[INIT] Archiving to: {ABS_OUTPUT_PATH}")
    try:
        canvas = init_canvas()
        user = canvas.get_current_user()
        print(f"Authenticated as: {user.name}")
        print("-" * 50)
    except Exception as e:
        print(f"[FATAL] Authentication failed: {e}")
        return

    try:
        pypandoc.get_pandoc_version()
    except OSError:
        print("[INIT] Pandoc not found. Downloading binary...")
        pypandoc.download_pandoc()

    courses = list(user.get_courses(enrollment_state='active'))

    for course in courses:
        if not hasattr(course, 'name'): continue
        safe_course_name = sanitize_filename(course.name)
        print(f"\n[COURSE] {safe_course_name}")

        try:
            modules = list(course.get_modules())
            for module in modules:
                safe_module_name = sanitize_filename(module.name)
                target_dir = os.path.join(ABS_OUTPUT_PATH, safe_course_name, safe_module_name)
                os.makedirs(target_dir, exist_ok=True)
                
                items = list(module.get_module_items())
                for item in items:
                    safe_title = sanitize_filename(item.title) or f"item_{item.id}"
                    
                    if item.type == 'File':
                        try:
                            file_obj = course.get_file(item.content_id)
                            ext = os.path.splitext(file_obj.filename)[1].lower()
                            clean_title = os.path.splitext(safe_title)[0]
                            save_path = os.path.join(target_dir, f"{clean_title}{ext}")
                            pdf_path = os.path.join(target_dir, f"{clean_title}.pdf")

                            if os.path.exists(save_path) or (ext in ['.doc', '.docx'] and os.path.exists(pdf_path)):
                                print(f"    [SKIP] Already archived: {clean_title}")
                                continue

                            if download_file(file_obj.url, save_path, file_obj.size):
                                if ext in ['.doc', '.docx']:
                                    convert_docx_to_pdf(save_path)
                        except Exception as e:
                            print(f"    [FAIL] File error: {e}")

                    elif item.type == 'Page':
                        clean_title = os.path.splitext(safe_title)[0]
                        save_path = os.path.join(target_dir, f"{clean_title}.pdf")
                        
                        if not os.path.exists(save_path):
                            try:
                                page_obj = course.get_page(item.page_url)
                                save_page_as_pdf(page_obj, save_path)
                            except Exception as e:
                                print(f"    [FAIL] Could not retrieve page {clean_title}: {e}")
                        else:
                            print(f"    [SKIP] Page already archived: {clean_title}")

        except Exception as e:
            print(f" [WARN] Skipping course {safe_course_name} due to error: {e}")

    print("\n" + "="*50)
    print(f"ARCHIVAL COMPLETE. FILES IN: {ABS_OUTPUT_PATH}")

if __name__ == "__main__":
    main()