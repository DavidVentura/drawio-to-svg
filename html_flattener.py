
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional


@dataclass
class TextToken:
    text: str
    bold: bool = False
    italic: bool = False
    color: Optional[str] = None

@dataclass
class NewlineToken:
    pass

class HTMLToTokenParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tokens: List[TextToken | NewlineToken] = []
        self.current_text = ""
        
        # State tracking
        self.bold = False
        self.italic = False
        self.color_stack: List[str] = []
    
    def handle_starttag(self, tag: str, attrs: List[tuple]):
        self._flush_text()
        
        if tag == "div":
            if self.tokens:
                self.tokens.append(NewlineToken())
        elif tag == "br":
            if self.tokens:
                self.tokens.append(NewlineToken())
        elif tag == "b":
            self.bold = True
        elif tag == "i":
            self.italic = True
        elif tag == "font":
            for attr, value in attrs:
                if attr == "color":
                    self.color_stack.append(value)
    
    def handle_endtag(self, tag: str):
        self._flush_text()
        
        if tag == "b":
            self.bold = False
        elif tag == "i":
            self.italic = False
        elif tag == "font":
            if self.color_stack:
                self.color_stack.pop()
    
    def handle_data(self, data: str):
        self.current_text += data
    
    def _flush_text(self):
        if not self.current_text:
            return
        
        token = TextToken(
            text=self.current_text,
            bold=self.bold,
            italic=self.italic,
            color=self.color_stack[-1] if self.color_stack else None
        )
        self.tokens.append(token)
        self.current_text = ""

def parse_html(html: str) -> List[TextToken | NewlineToken]:
    parser = HTMLToTokenParser()
    parser.feed(html)
    parser._flush_text()  # Flush any remaining text
    return parser.tokens

# Example usage:
if __name__ == "__main__":
    html = 'TC <b><i>asd</i></b><div><font color="#2414ff"><b>qwe</b></font> r</div><div>ty</div>'
    html ='<font color="#87ff2b">TC <b><i>asd</i></b></font><div><b style=""><font color="#ff2e2e">qwe</font></b><font color="#87ff2b"> r</font></div><div><font color="#87ff2b">ty</font></div>'
    tokens = parse_html(html)
    
    # Print tokens for visualization
    for token in tokens:
        if isinstance(token, NewlineToken):
            print("NEWLINE")
        else:
            print(f"Text: '{token.text}', Bold: {token.bold}, "
                  f"Italic: {token.italic}, Color: {token.color}")
