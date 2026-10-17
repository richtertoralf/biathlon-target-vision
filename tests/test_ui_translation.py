"""Übersetzungsschutz aller eigenen HTML-Seiten und verbindliche Sportbegriffe."""
from html.parser import HTMLParser
from pathlib import Path
import unittest


STATIC = Path(__file__).resolve().parents[1] / 'biathlon_target_vision' / 'static'


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__();self.root=None;self.meta=[];self.translate_yes=False;self.feed(text)

    def handle_starttag(self, tag, attrs):
        attributes=dict(attrs)
        if tag == 'html':self.root=attributes
        if tag == 'meta':self.meta.append(attributes)
        if attributes.get('translate') == 'yes':self.translate_yes=True


class UiTranslationTests(unittest.TestCase):
    def test_every_html_document_disables_automatic_translation(self):
        pages=list(STATIC.glob('*.html'));self.assertGreaterEqual(len(pages),4)
        for page in pages:
            with self.subTest(page=page.name):
                document=Document(page.read_text())
                self.assertEqual(document.root['translate'],'no')
                self.assertIn('notranslate',document.root['class'].split())
                self.assertIn(document.root['lang'],('en','de','cs'))
                self.assertIn({'name':'google','content':'notranslate'},document.meta)
                self.assertFalse(document.translate_yes)

    def test_reported_browser_mistranslations_are_absent_from_original_files(self):
        for page in STATIC.iterdir():
            if page.suffix not in ('.html','.js'):continue
            with self.subTest(page=page.name):
                text=page.read_text()
                self.assertNotRegex(text,r'(?i)\b(?:Fahrspuren|Strecke\s+\d+|Errichtet|Bevorzugt)\b')
