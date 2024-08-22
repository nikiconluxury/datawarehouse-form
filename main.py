from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import Optional
import uvicorn, os, uuid, boto3
from sqlalchemy import create_engine, text
# from dotenv import load_dotenv
# load_dotenv()
app = FastAPI()
templates = Jinja2Templates(directory="templates/")
pwd_value = os.environ.get('MSSQLS_PWD')
pwd_str =f"Pwd={pwd_value};"
global conn
conn = "DRIVER={ODBC Driver 17 for SQL Server};Server=35.172.243.170;Database=luxurymarket_p4;Uid=luxurysitescraper;" + pwd_str
global engine
engine = create_engine("mssql+pyodbc:///?odbc_connect=%s" % conn)


def get_s3_client():
    session = boto3.session.Session()
    client = boto3.client(service_name='s3',
                          region_name=os.getenv('REGION'),
                          aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                          aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))
    return client

def upload_file_to_space(file_src, save_as, is_public=True):
    spaces_client = get_s3_client()
    space_name = 'iconluxurygroup-s3'  # Your space name

    spaces_client.upload_file(file_src, space_name, save_as, ExtraArgs={'ACL': 'public-read'})
    print(f"File uploaded successfully to {space_name}/{save_as}")
    
    if is_public:
        upload_url = f"https://iconluxurygroup-s3.s3.us-east-2.amazonaws.com/{save_as}"
        print(f"Public URL: {upload_url}")
        return upload_url


def insert_upload_records(data):
    # Unpacking the data dictionary
    original_filename = data.get("original_filename")
    s3_url = data.get("s3_url")
    notes = data.get("notes")
    currency = data.get("currency")
    option = data.get("option")
    
    # Define the SQL statement with placeholders
    sql = ("""
        INSERT INTO utb_WarehouseFiles (FileName, FileLocationURL, FileMemo, CurrencyID, ColorToModel)
        VALUES (:file_name, :file_url, :memo_message, :currency_option, :color_option)
    """)

    # Create a connection and execute the SQL statement with the unpacked data
    connection = engine.connect()
    sql = text(sql)

    # Use a parameterized query to safely insert the values
    connection.execute(sql, {
        "file_name": original_filename,
        "file_url": s3_url,
        "memo_message": notes,
        "currency_option": currency,
        "color_option": option
    })

    # Commit the transaction and close the connection
    connection.commit()
    connection.close()

    print(f"Writing data to database:\n"
      f"Original Filename: {original_filename}\n"
      f"S3 URL: {s3_url}\n"
      f"Notes: {notes}\n"
      f"Currency: {currency}\n"
      f"Option: {option}")

    return True



# Route to handle GET requests and render the form
@app.get("/form", response_class=HTMLResponse)
async def form_get(request: Request):
    return templates.TemplateResponse("form.html", context={"request": request, "message": {"text": ""}})

@app.post("/form")
async def form_post(
    request: Request,
    fileUpload: Optional[UploadFile] = File(None),
    currency: int = Form(...),
    option: int = Form(...),
    notes: Optional[str] = Form(None),
):
    # Check if fileUpload is empty
    if fileUpload is None or fileUpload.filename == "":
        # Return an error message in the form if no file is uploaded
        return templates.TemplateResponse("form.html", context={"request": request, "message": {"text": "Error: A file is required.", "type": "error"}})
    
    # Specify the directory where you want to save the file temporarily
    save_directory = "uploads"
    
    # Ensure the directory exists, create it if it doesn't
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)
    
    # Read the original file name and extension
    original_filename = fileUpload.filename
    file_extension = os.path.splitext(original_filename)[1]  # Get the file extension
    
    # Generate a unique identifier (UUID) for the file
    unique_id = uuid.uuid4()
    unique_filename = f"{unique_id}{file_extension}"  # Use the original file extension
    
    # Define the full file path with the UUID for temporary saving
    temp_file_path = os.path.join(save_directory, unique_filename)
    
    # Save the uploaded file to the specified directory temporarily
    with open(temp_file_path, "wb") as buffer:
        buffer.write(await fileUpload.read())
    
    # Upload the file to S3
    s3_key = f"Datawarehouseload/files/{unique_filename}"
    s3_url = upload_file_to_space(temp_file_path, s3_key)
    
    # Prepare data for database write, including the original file name and the S3 key
    data = {
        "currency": currency,
        "option": option,
        "notes": notes,
        "original_filename": original_filename,
        "s3_key": s3_key,
        "s3_url": s3_url,
    }
    
    # Simulate database write with the file's metadata
    insert_upload_records(data)
    
    # Clean up the temporary file
    os.remove(temp_file_path)
    
    # Return a success message and clear the form
    return templates.TemplateResponse("form.html", context={"request": request, "message": {"text": "File uploaded successfully. The form is ready for the next submission.", "type": "success"}})

# Optional: Route to handle the root URL
@app.get("/")
async def root():
    return {"message": "Welcome to the file upload service!"}

if __name__ == "__main__":
    uvicorn.run("main:app", port=8080, log_level="info", host="0.0.0.0")
