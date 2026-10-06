"""Render sample_data/handbook.pdf, a fictional course handbook used for the demo.

The content is invented on purpose: the chatbot can only answer these questions from the
knowledge base, which makes grounding easy to show. Run from backend/:
    python scripts/make_sample_pdf.py
"""

from pathlib import Path

from fpdf import FPDF

OUTPUT = Path(__file__).resolve().parents[2] / "sample_data" / "handbook.pdf"
TITLE = "CS 4780 Applied Machine Learning - Course Handbook (Northbridge Institute, Fall 2026)"

PAGES: list[list[tuple[str, str]]] = [
    [
        ("Course overview",
         "CS 4780 Applied Machine Learning is a 4-credit course taught at the Northbridge "
         "Institute of Technology. It covers supervised learning, model evaluation, neural "
         "networks and retrieval-augmented generation. Lectures take place on Mondays and "
         "Wednesdays from 10:00 to 11:30 in the Halvorsen Building, room 1.14."),
        ("Course staff",
         "The lecturer is Dr. Miriam Okonkwo-Lindqvist. The two teaching assistants are "
         "Tomas Beaulieu and Priya Ramanathan. The course mailbox is "
         "cs4780-staff@northbridge.example; staff answer emails within two working days."),
        ("Office hours",
         "Dr. Okonkwo-Lindqvist holds office hours on Tuesdays from 14:00 to 16:00 in room 3.07. "
         "Teaching assistant office hours are on Thursdays from 16:00 to 18:00 in the Ada Lab. "
         "During the final project weeks, an extra office hour runs on Fridays at 12:00 online."),
    ],
    [
        ("Grading",
         "The final grade is made up of four parts: weekly quizzes count for 10 percent, the "
         "three lab assignments count for 30 percent, the midterm exam counts for 20 percent, "
         "and the final project counts for 40 percent. A final grade of 55 percent or higher is "
         "required to pass the course."),
        ("Quizzes",
         "Quizzes are released every Monday at 09:00 and close on Sunday at 23:59. The two lowest "
         "quiz scores are dropped automatically. Quizzes cannot be retaken."),
        ("Midterm exam",
         "The midterm exam is a 90-minute written exam held in week 8. Students may bring one "
         "double-sided A4 sheet of handwritten notes. Calculators are allowed, but phones and "
         "laptops are not."),
    ],
    [
        ("Late submission policy",
         "Lab assignments submitted late lose 10 percent of the available points per day, for a "
         "maximum of three days. After three days the submission receives zero points. Every "
         "student has two grace days for the whole semester that can be used on lab assignments "
         "without penalty. Grace days cannot be used for the final project."),
        ("Extensions",
         "Extensions beyond the grace days are only granted for documented illness or family "
         "emergencies. Requests must be sent to the course mailbox before the deadline whenever "
         "possible, together with supporting documentation."),
    ],
    [
        ("Final project",
         "The final project is done in teams of three students. Teams must register their topic "
         "by the end of week 6. Each team builds a working machine learning application, writes "
         "a report of at most eight pages, and gives a ten-minute live demo in week 14."),
        ("Project grading",
         "The project grade is split into the working demo (40 percent), the written report "
         "(35 percent), code quality and documentation (15 percent), and the peer review "
         "(10 percent). All team members receive the same grade unless the peer review shows a "
         "clearly unequal contribution."),
        ("Project rules",
         "Code must be kept in a version-controlled repository that the teaching assistants can "
         "access. Pretrained models and public APIs may be used, but the report must state "
         "clearly which parts the team built themselves."),
    ],
    [
        ("Lab schedule",
         "Lab 1 (data cleaning and baselines) is due in week 3. Lab 2 (model evaluation and "
         "cross-validation) is due in week 5. Lab 3 (neural networks with PyTorch) is due in "
         "week 10. All labs are due on Fridays at 17:00 and are submitted through the course "
         "portal."),
        ("Compute resources",
         "Every student receives 40 GPU hours on the Northbridge Orca cluster. Extra hours can be "
         "requested by the team leader for the final project, up to 60 additional hours per team. "
         "Jobs that run longer than 12 hours are stopped automatically."),
    ],
    [
        ("Academic integrity",
         "Students may discuss ideas with each other, but all submitted code and text must be "
         "their own. Using AI assistants is allowed for lab assignments only if the use is "
         "declared in a short note at the top of the submission. Undeclared use is treated as "
         "plagiarism and reported to the examination board."),
        ("Attendance",
         "Lecture attendance is not mandatory, but attendance at the week 14 project demos is "
         "required for all students. Missing your own team's demo without a valid reason results "
         "in a zero for the demo component."),
    ],
]  # fmt: skip


def build() -> None:
    pdf = FPDF()
    pdf.set_title(TITLE)
    pdf.set_auto_page_break(auto=True, margin=15)
    for number, sections in enumerate(PAGES, start=1):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(0, 6, TITLE, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        for heading, body in sections:
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 6, body, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 10, f"Page {number}", align="C")
    OUTPUT.parent.mkdir(exist_ok=True)
    pdf.output(str(OUTPUT))


if __name__ == "__main__":
    build()
