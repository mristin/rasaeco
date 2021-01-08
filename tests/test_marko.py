import textwrap
import unittest

import marko


class TestTagsAndCode(unittest.TestCase):
    def test_that_too_few_newlines_dont_work(self) -> None:
        text = textwrap.dedent(
            """\
            <model name="something">
            ```
            some code
            ```
            </model>
            """
        )

        document = marko.convert(text)
        self.assertEqual(
            '<model name="something">\n```\nsome code\n```\n</model>\n', document
        )

    def test_the_necessary_newlines(self) -> None:
        text = textwrap.dedent(
            """\
            <model name="something">
            
            ```
            some code
            ```
            
            </model>
            """
        )

        document = marko.convert(text)
        self.assertEqual(
            '<model name="something">\n<pre><code>some code\n</code></pre>\n</model>\n',
            document,
        )

    def test_too_few_new_lines_when_two_paragraphs(self) -> None:
        text = textwrap.dedent(
            """\
            <model name="something">
            first line
            
            second line
            </model>
            """
        )

        document = marko.convert(text)
        # This is actually incorrect HTML and a bug in marko.
        self.assertEqual(
            '<model name="something">\nfirst line\n<p>second line\n</model></p>\n',
            document,
        )

    def test_sufficient_new_lines_when_two_paragraphs(self) -> None:
        text = textwrap.dedent(
            """\
            <model name="something">
            
            first line

            second line
            
            </model>
            """
        )

        document = marko.convert(text)
        self.assertEqual(
            '<model name="something">\n'
            "<p>first line</p>\n"
            "<p>second line</p>\n"
            "</model>\n",
            document,
        )

    def test_tag_surrounding_two_paragraphs_without_newlines(self) -> None:
        text = textwrap.dedent(
            """\
            <model name="something">first line
            
            second line</model>"""
        )

        document = marko.convert(text)
        # This is actually incorrect HTML and a bug in marko.
        self.assertEqual(
            '<p><model name="something">first line</p>\n<p>second line</model></p>\n',
            document,
        )

    def test_tag_surrounding_multiline_paragraph(self) -> None:
        text = textwrap.dedent(
            """\
            <model name="something">first line
            second line</model>"""
        )

        document = marko.convert(text)
        self.assertEqual(
            '<p><model name="something">' "first line\n" "second line</model></p>\n",
            document,
        )

    def test_tag_surrounding_multiline_paragraph_with_newlines(self) -> None:
        text = textwrap.dedent(
            """\
            <model name="something">
            
            first line
            second line
            
            </model>"""
        )

        document = marko.convert(text)
        self.assertEqual(
            '<model name="something">\n' "<p>first line\nsecond line</p>\n" "</model>",
            document,
        )


if __name__ == "__main__":
    unittest.main()
