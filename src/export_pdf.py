"""
Экспорт диалога в PDF с выделением источников
"""
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.lib.colors import HexColor
from sqlalchemy.orm import Session
from io import BytesIO
from .models import Dialogue, Message, Citation


def export_dialogue_to_pdf(db: Session, dialogue_id: int) -> bytes:
    """Экспорт диалога в PDF"""
    dialogue = db.query(Dialogue).filter(Dialialogue.id == dialogue_id).first()
    if not dialogue:
        raise ValueError(f"Диалог {dialogue_id} не найден")

    messages = db.query(Message).filter(Message.dialogue_id == dialogue_id).order_by(Message.timestamp).all()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Title'], fontSize=16, alignment=TA_LEFT)
    user_style = ParagraphStyle('UserStyle', parent=styles['Normal'], textColor=HexColor('#1a73e8'), leftIndent=20)
    assistant_style = ParagraphStyle('AssistantStyle', parent=styles['Normal'], textColor=HexColor('#0d652d'),
                                     leftIndent=20)
    citation_style = ParagraphStyle('CitationStyle', parent=styles['Normal'], fontSize=9, textColor=HexColor('#666666'),
                                    leftIndent=40)

    story = []
    story.append(Paragraph(f"Диалог #{dialogue_id}", title_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Дата: {dialogue.started_at.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 24))

    for msg in messages:
        if msg.sender == "user":
            story.append(Paragraph(f"👤 Врач: {msg.message_text}", user_style))
        else:
            story.append(Paragraph(f"🤖 Ассистент: {msg.message_text}", assistant_style))
            citations = db.query(Citation).filter(Citation.message_id == msg.id).all()
            for cit in citations:
                text = f"📚 Источник: {cit.source_title}"
                if cit.page_number:
                    text += f", стр. {cit.page_number}"
                story.append(Paragraph(text, citation_style))
        story.append(Spacer(1, 12))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()