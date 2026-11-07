"""
Users passes the JD

Load resume
Load cover letters
Load skills

Connect to LLM

Instruct LLM to return:
- COMPANY
- JOB_TITLE
- cover letter text (CONTENT)

Read Template doc

Take LLM output and write to template
"""
import argparse
import io
import os
import smtplib
from email.mime.text import MIMEText

import boto3
import PyPDF2
from docx import Document
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

load_dotenv()

def send_user_email(body :str, subject: str):
    """
    Docstring for send_user_email
    
    :param body: Information to include in the email body
    
    Sends an email with the provided body content to a predefined recipient.
    """
    # Email details
    sender = os.environ["GMAIL_USERNAME"]
    receiver = [os.environ["GMAIL_USERNAME"]]
    password = os.environ["GMAIL_PASSWORD"]  # or GMAIL_APP_PASSWORD

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(receiver)

    # Send email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())


def extract_text_from_pdf(s3, bucket, file_path: str) -> str:
    """Read all text from a PDF file."""
    
    response = s3.get_object(Bucket=bucket, Key=file_path)
    pdf_file = io.BytesIO(response['Body'].read())
    text_parts = []
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        if page_text.strip():
            text_parts.append(page_text)
    
    return "\n".join(text_parts)

def extract_text_from_docx(s3, bucket,  file_path: str) -> str:
    """Read all paragraph text from a .docx file."""
    response = s3.get_object(Bucket=bucket, Key=file_path)
    docx_file = io.BytesIO(response['Body'].read())
    doc = Document(docx_file)
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def extract_text_from_markdown_s3(s3, bucket,  file_path: str) -> str:
    """Read all content from a Markdown file and return it as one string."""
    response = s3.get_object(Bucket=bucket, Key=file_path)
    file_content = response['Body'].read().decode('utf-8')
    #with open(file_path, 'r', encoding='utf-8') as file:
    #    return file.read()
    return file_content

def extract_text_from_markdown_local(file_path: str) -> str:
    """Read all content from a Markdown file and return it as one string."""
    #response = s3.get_object(Bucket=bucket, Key=file_path)
    #file_content = response['Body'].read().decode('utf-8')
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()
    #return file_content


class OutputCoverLetter(BaseModel):
    """How to return output from the agent"""
    CONCERNS: str = Field(description="Concerns the LLM has about appling for this job ad")
    COMPANY: str = Field(description="Name of the company the job is for")
    JOB_TITLE: str = Field(description="The title of the job")
    CONTENT: str = Field(description="The complete cover letter")
    NOTES: str = Field(description="Note for Anthony to action from this cover letter")



#KNOWLEDGE_DIR = "./Knowledge/" # For local runs

#user_input = """
#
# """

def main(user_input: str):
    mob_num = os.getenv("MOB_NUM", None) # Mobile phone number to make sure never get through to OpenAI
    gmail = os.getenv("GMAIL_USERNAME", None) # email to make sure never get through to OpenAI
    s3_bucket_name = os.environ["AWS_BUCKET_NAME"]

    s3 = boto3.client(
            "s3",
            aws_access_key_id=os.environ["AWS_ACCESS_KEY"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            region_name="ap-southeast-2",
        )

    # Get Knowledge from S3
    resume = extract_text_from_pdf(s3, s3_bucket_name, "ACutajar_Resume.pdf") # Read resume
    covlet = extract_text_from_docx(s3, s3_bucket_name, "Asahi.docx") # Read Cover Letter
    skills = extract_text_from_markdown_s3(s3, s3_bucket_name, "anthony_cutajar_skills.md") # Read Skills

    SYSTEM_PROMPT = extract_text_from_markdown_local("cover_letter_agent_system_prompt.md") # Read sys prompt

    # Insert texts into the sys prompt
    SYSTEM_PROMPT = SYSTEM_PROMPT.replace("{{RESUME}}", resume)
    SYSTEM_PROMPT = SYSTEM_PROMPT.replace("{{PREVIOUS_COVER_LETTERS}}", covlet)
    SYSTEM_PROMPT = SYSTEM_PROMPT.replace("{{SKILLS_DOCUMENT}}", skills)

    # Sanitized the System prompt
    if mob_num:
        SYSTEM_PROMPT = SYSTEM_PROMPT.replace(mob_num, "XXXXXXXXXXXXX") # Blank the mobile numbers
        
    if gmail:
        SYSTEM_PROMPT = SYSTEM_PROMPT.replace(gmail, "XXXXXXXXXXXXX") # Blank the email

    # Create agent
    agent = create_agent( # Define the agent
            ChatOpenAI(model="gpt-4o", api_key=os.environ["OPENAI_API_KEY"]), 
            #tools=[query_embeddings, search_tool],
            #checkpointer=InMemorySaver(),
            system_prompt=SYSTEM_PROMPT,
            response_format=OutputCoverLetter
        )

    # Send the jd
    response = agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]},
                {"configurable": {"thread_id": "1"}},
            )
    CONCERNS = response['structured_response'].CONCERNS
    COMPANY = response['structured_response'].COMPANY
    JOB_TITLE = response['structured_response'].JOB_TITLE
    CONTENT = response['structured_response'].CONTENT
    NOTES = response['structured_response'].NOTES

    #print(CONTENT)
    #print(COMPANY)
    #print(JOB_TITLE)
    #print(NOTES)
    #print(CONCERNS)

    # Email the output
    send_user_email(f"{NOTES}\n{CONCERNS}\n\n{CONTENT}", f"{COMPANY} - {JOB_TITLE}")

    #with open("cv.md",'w') as f:
    #    f.write(CONTENT)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Write a Cover Letter for a Job")
    p.add_argument("jd", help="The Job Description")
    
    args = p.parse_args()
    
    main(args.jd)