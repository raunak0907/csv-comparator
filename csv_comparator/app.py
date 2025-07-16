from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
import os
import pandas as pd
import csv
from datetime import datetime
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Table, TableStyle, Paragraph, Spacer, KeepTogether
)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = 'supersecretkey'

UPLOAD_FOLDER = 'uploads'
EXCLUDE_COLUMNS = ['YYYYMM']
YOUR_EMAIL = "2005raunakrathor@gmail.com"
APP_PASSWORD = "dlovdcwvocundebw"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def read_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return {row['SAIL_PERNO']: row for row in reader}

def compare_files(master_path, slave_path):
    master_data = read_csv(master_path)
    slave_data = read_csv(slave_path)

    all_columns = {col for dataset in [master_data, slave_data]
                   for row in dataset.values() for col in row if col not in EXCLUDE_COLUMNS}

    diffs, new_joiners = [], []
    for emp_key in set(master_data) | set(slave_data):
        m_row = master_data.get(emp_key, {})
        s_row = slave_data.get(emp_key, {})

        if not m_row:
            changes = [{'Field': col, 'Old': '', 'New': s_row[col]} for col in s_row if col not in EXCLUDE_COLUMNS and s_row.get(col)]
            if changes:
                new_joiners.append({'Employee': emp_key, 'Changes': changes})
        elif not s_row:
            continue
        else:
            changes = [{'Field': col, 'Old': m_row.get(col, '').strip(), 'New': s_row.get(col, '').strip()}
                       for col in all_columns if m_row.get(col, '').strip() != s_row.get(col, '').strip()]
            if changes:
                diffs.append({'Employee': emp_key, 'Changes': changes})
    return diffs, new_joiners

def send_email(recipient, subject, body, attachment_buffer, filename):
    try:
        attachment_buffer.seek(0)
        pdf_data = attachment_buffer.read()
        attachment_buffer.seek(0)

        msg = MIMEMultipart()
        msg['From'] = YOUR_EMAIL
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        attachment = MIMEApplication(pdf_data, _subtype="pdf")
        attachment.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(attachment)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(YOUR_EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()

        print(f"✅ Email sent to {recipient}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

@app.route("/", methods=["GET", "POST"])
def index():
    diff, new = [], []
    if request.method == "POST":
        master_file = request.files['master']
        slave_file = request.files['slave']

        if not master_file or not slave_file:
            flash("Please upload both CSV files.", "danger")
            return redirect(url_for('index'))

        master_path = os.path.join(UPLOAD_FOLDER, "master.csv")
        slave_path = os.path.join(UPLOAD_FOLDER, "slave.csv")
        master_file.save(master_path)
        slave_file.save(slave_path)

        session['master_path'] = master_path
        session['slave_path'] = slave_path

        diff, new = compare_files(master_path, slave_path)

    return render_template("index.html", diff=diff, new=new)

def generate_pdf(data, category, perno_map):
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    wrap = ParagraphStyle(name='wrap', parent=styles['BodyText'], fontSize=9)
    header_style = ParagraphStyle(name='header', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor("#003366"), alignment=1)
    desc_style = ParagraphStyle(name='desc', parent=styles['Normal'], fontSize=10, spaceAfter=12, alignment=1)

    elements = []

    title = "Differences Report" if category == "diff" else "New Joinees Report"
    date_str = datetime.now().strftime('%B %d, %Y')

    elements.append(Paragraph(f"<b>Date:</b> {date_str}", styles['Normal']))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("Employee Comparison Report", header_style))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("This report summarizes employee data changes or new joiners by comparing the uploaded master and slave CSV files.", desc_style))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(f"<b>{title}</b>", styles['Heading2']))
    elements.append(Spacer(1, 0.2 * inch))

    for group in data:
        unit_id = perno_map.get(group['Employee'], group['Employee'])
        elements.append(Paragraph(f"<font size=11><b>Unit Perno:</b> {unit_id}</font>", styles['Heading4']))
        elements.append(Spacer(1, 0.1 * inch))

        if category == "diff":
            table_data = [["Field", "Old", "New"]]
            for c in group['Changes']:
                table_data.append([
                    Paragraph(c['Field'], wrap),
                    Paragraph(c['Old'], wrap),
                    Paragraph(c['New'], wrap)
                ])
        else:
            fields_to_show = ['SAIL_PERNO', 'UNIT_PERNO', 'DATE_OF_JOINING', 'IFSC_CODE', 'EMP_NAME']
            table_data = [["Field", "Value"]]
            for c in group['Changes']:
                if c['Field'] in fields_to_show:
                    table_data.append([
                        Paragraph(c['Field'], wrap),
                        Paragraph(c['New'], wrap)
                    ])

        col_widths = [120, 170, 170] if category == "diff" else [120, 340]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#003366")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        elements.append(KeepTogether([table]))
        elements.append(Spacer(1, 0.25 * inch))
        elements.append(Spacer(1, 0.05 * inch))

    def add_page_number(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(A4[0] - 40, 20, f"Page {canvas.getPageNumber()}")

    doc = BaseDocTemplate(buffer, pagesize=A4,
                          rightMargin=40, leftMargin=40,
                          topMargin=72, bottomMargin=72)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    doc.addPageTemplates([PageTemplate(id='PageNum', frames=frame, onPage=add_page_number)])

    doc.build(elements)
    buffer.seek(0)
    return buffer

@app.route("/send_email", methods=["POST"])
def send_email_route():
    recipient = request.form.get('recipient')
    category = request.form.get('report_type')

    master_path = session.get('master_path')
    slave_path = session.get('slave_path')

    if not recipient or not category or not master_path or not slave_path:
        flash("Missing data for email.", "danger")
        return redirect(url_for('index'))

    diff, new = compare_files(master_path, slave_path)
    data = diff if category == "diff" else new

    data_source = read_csv(master_path) or read_csv(slave_path)
    perno_map = {k: v.get("UNIT_PERNO", k) for k, v in data_source.items()}

    pdf_buffer = generate_pdf(data, category, perno_map)
    success = send_email(recipient, f"{category.capitalize()} Report", "Please find the report attached.", pdf_buffer, f"{category}_report.pdf")

    flash(f"Email {'sent' if success else 'sending failed.'}", "success" if success else "danger")
    return redirect(url_for('index'))

@app.route("/download/<category>")
def download_pdf(category):
    master_path = session.get('master_path')
    slave_path = session.get('slave_path')

    if not master_path or not slave_path:
        return "No comparison data found. Please re-upload the files.", 400

    diff, new = compare_files(master_path, slave_path)
    data = diff if category == "diff" else new

    data_source = read_csv(master_path) or read_csv(slave_path)
    perno_map = {k: v.get("UNIT_PERNO", k) for k, v in data_source.items()}

    pdf_buffer = generate_pdf(data, category, perno_map)
    return send_file(pdf_buffer, as_attachment=True, download_name=f"{category}_report.pdf")

@app.route("/download_excel")
def download_excel():
    master_path = session.get('master_path')
    slave_path = session.get('slave_path')

    if not master_path or not slave_path:
        return "Please upload and compare files first."

    diff, new = compare_files(master_path, slave_path)

    output_path = os.path.join(UPLOAD_FOLDER, "comparison_results.xlsx")
    with pd.ExcelWriter(output_path) as writer:
        for name, records in zip(['Differences', 'New_Joinees'], [diff, new]):
            rows = []
            for group in records:
                for change in group['Changes']:
                    rows.append({
                        'Employee': group['Employee'],
                        'Field': change['Field'],
                        'Old Value': change['Old'],
                        'New Value': change['New']
                    })
            if rows:
                pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False)

    return send_file(output_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True) 