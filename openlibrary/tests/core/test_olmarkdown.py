from openlibrary.core.olmarkdown import OLMarkdown

def test_olmarkdown():
    def md(text):
        return OLMarkdown(text).convert().strip()

    def p(html):
        # markdown always wraps the result in <p>.
        return "<p>%s\n</p>" % html

    assert md("**foo**") == p("<strong>foo</strong>")
    assert md("<b>foo</b>") == p('<b>foo</b>')
    assert md("https://openlibrary.org") == p(
            '<a href="https://openlibrary.org" rel="nofollow">' +
                'https://openlibrary.org' +
            '</a>'
        )

    # why extra spaces?
    assert md("a\nb") == p("a<br/>\n   b")
