from formatted_text import FormattedText, Format

if __name__ == "__main__":
    html_text: str = "<b>ab<u>cd</u>ef<i><s>gh</s>jk</i>lm</b>no"
    formatted_text: FormattedText = FormattedText(html_text)
    for text, text_format in formatted_text:
        print(text, ":", *text_format)
