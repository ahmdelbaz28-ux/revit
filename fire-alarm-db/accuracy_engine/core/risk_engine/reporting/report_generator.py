"""PDF report generator using reportlab."""


def generate_report(results: list, filename: str = "risk_report.pdf"):
    """Generate PDF risk assessment report.
    
    Args:
        results: List of RiskResult objects
        filename: Output PDF filename
        
    Returns:
        Path to generated PDF file
    """
    # Import reportlab - raise error if not available
    try:
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
    except ImportError:
        # Fallback if reportlab not installed - create text file instead
        import os
        base = os.path.splitext(filename)[0] + ".txt"
        with open(base, 'w') as f:
            f.write("FireAlarmAI Safety Risk Assessment Report\n")
            f.write("=" * 50 + "\n\n")
            for r in results:
                if hasattr(r, 'room_id'):
                    f.write(f"Room: {r.room_id}\n")
                    f.write(f"Risk Level: {r.risk_level}\n")
                    f.write(f"Score: {r.score:.1f}\n")
                    f.write(f"Confidence: {r.confidence:.1%}\n")
                    f.write(f"Recommendations: {', '.join(r.recommendations) if r.recommendations else 'None'}\n")
                else:
                    f.write(f"Room: {r.get('room_id', 'unknown')}\n")
                    f.write(f"Risk Level: {r.get('risk_level', 'unknown')}\n")
                f.write("-" * 30 + "\n\n")
        return base
    
    # Build PDF with reportlab
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title = Paragraph("<b>FireAlarmAI Safety Risk Assessment Report</b>", styles["Title"])
    elements.append(title)
    elements.append(Spacer(1, 20))

    # Results for each room
    for r in results:
        if hasattr(r, 'room_id'):
            room_id = r.room_id
            risk_level = r.risk_level
            score = r.score
            confidence = r.confidence
            recommendations = r.recommendations
        else:
            room_id = r.get("room_id", "unknown")
            risk_level = r.get("risk_level", "unknown")
            score = r.get("score", 0)
            confidence = r.get("confidence", 0)
            recommendations = r.get("recommendations", [])

        # Color code the risk level
        color = "green"
        if risk_level == "CRITICAL":
            color = "red"
        elif risk_level == "HIGH":
            color = "orange"
        elif risk_level == "MEDIUM":
            color = "blue"

        text = f"""
        <b>Room:</b> {room_id}<br/>
        <b>Risk Level:</b> <font color="{color}">{risk_level}</font><br/>
        <b>Score:</b> {score:.1f}<br/>
        <b>Confidence:</b> {confidence:.1%}<br/>
        <b>Recommendations:</b> {', '.join(recommendations) if recommendations else 'None'}
        """
        elements.append(Paragraph(text, styles["BodyText"]))
        elements.append(Spacer(1, 10))

    doc.build(elements)
    return filename
