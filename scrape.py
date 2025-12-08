import os
import requests
from canvasapi import Canvas
from pathvalidate import sanitize_filename
from tqdm import tqdm #For visual sanity
from dotenv import load_dotenv


load_dotenv() 

# --- CONFIGURATION ---
# Access environment variables
API_URL = os.getenv("CANVAS_API_URL", "https://dlsu.instructure.com") 
API_KEY = os.getenv("CANVAS_API_KEY") 
OUTPUT_DIR = "DLSU_Canvas_Archive"

if not API_KEY:
    raise ValueError("FATAL: CANVAS_API_KEY not found. Check your .env file.")

def init_canvas():
    """Initialize the Canvas object."""
    return Canvas(API_URL, API_KEY)

def download_file(url, filepath, file_size):
    """Downloads a file with a progress bar."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # tqdm progress bar setup
        with open(filepath, 'wb') as f, tqdm(
            desc=os.path.basename(filepath),
            total=file_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
            leave=False # Clears bar after completion to keep logs clean
        ) as bar:
            for chunk in response.iter_content(chunk_size=8192):
                size = f.write(chunk)
                bar.update(size)
        return True
    except Exception as e:
        print(f"    [ERROR] Download failed: {e}")
        if os.path.exists(filepath):
            os.remove(filepath) # Clean up partial files
        return False

def save_page_content(page, output_path):
    """Saves Canvas Page HTML body to a file."""
    try:
        if hasattr(page, 'body') and page.body:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"<h1>{page.title}</h1>\n") # Add title to content
                f.write(page.body)
            print(f"    [HTML] Saved Page: {os.path.basename(output_path)}")
        else:
            pass # Silent skip for empty pages
    except Exception as e:
        print(f"    [ERROR] Page save failed: {e}")

def main():
    try:
        canvas = init_canvas()
        user = canvas.get_current_user()
        print(f"Authenticated as: {user.name}")
        print("-" * 50)
    except Exception as e:
        print(f"[FATAL] Authentication failed. Check your token. Error: {e}")
        return

    courses = user.get_courses(enrollment_state='active')

    for course in courses:
        if not hasattr(course, 'name'): continue

        safe_course_name = sanitize_filename(course.name)
        print(f"\n[COURSE] {safe_course_name}")

        try:
            modules = course.get_modules()
            # Convert to list to check if empty, though slightly inefficient, it's safer for loops (I'm not explaning why)
            for module in modules:
                safe_module_name = sanitize_filename(module.name)
                target_dir = os.path.join(OUTPUT_DIR, safe_course_name, safe_module_name)
                os.makedirs(target_dir, exist_ok=True)
                
                # Get items
                items = list(module.get_module_items())
                
                for item in items:
                    safe_title = sanitize_filename(item.title)
                    
                    # 1. FILES
                    if item.type == 'File':
                        try:
                            # We must fetch the file object to get the download URL and size
                            file_obj = course.get_file(item.content_id)
                            ext = os.path.splitext(file_obj.filename)[1]
                            save_path = os.path.join(target_dir, f"{safe_title}{ext}")
                            
                            if not os.path.exists(save_path):
                                download_file(file_obj.url, save_path, file_obj.size)
                            else:
                                print(f"    [SKIP] Already exists: {safe_title}")
                        except Exception as e:
                            print(f"    [FAIL] Access denied to file: {safe_title}")

                    # 2. PAGES
                    elif item.type == 'Page':
                        try:
                            page_obj = course.get_page(item.page_url)
                            save_path = os.path.join(target_dir, f"{safe_title}.html")
                            if not os.path.exists(save_path):
                                save_page_content(page_obj, save_path)
                        except Exception as e:
                            print(f"    [FAIL] Access denied to page: {safe_title}")

                    # 3. URLS
                    elif item.type == 'ExternalUrl':
                        save_path = os.path.join(target_dir, f"{safe_title}_Link.url")
                        # .url format works like a shortcut in Windows/macOS
                        with open(save_path, 'w') as f:
                            f.write(f"[InternetShortcut]\nURL={item.external_url}")

        except Exception as e:
            print(f"  [WARN] Issue accessing modules for {safe_course_name}. Skipping.")

    print("\n" + "="*50)
    print("ARCHIVAL COMPLETE. DATA SECURED.")

if __name__ == "__main__":
    main()