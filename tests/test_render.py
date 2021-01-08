import textwrap
import unittest

import rasaeco.render


class TestNewlineTrimming(unittest.TestCase):
    def test_self_closing_tag_re(self) -> None:
        text = "<something/>"
        mtch = rasaeco.render._TAG_SELF_CLOSING_RE.match(text)
        assert mtch is not None
        self.assertEqual(text, mtch.group())

    def test_empty_string(self) -> None:
        text = ""
        trimmed = rasaeco.render._trim_newlines_around_tags(text=text)

        self.assertEqual("", trimmed)

    def test_no_new_lines_to_trim(self) -> None:
        text = "prefix\n\n<some-tag>say\nsomething</some-tag>\nsuffix"
        trimmed = rasaeco.render._trim_newlines_around_tags(text=text)

        self.assertEqual(text, trimmed)

    def test_self_closing_tag(self) -> None:
        text = "prefix\n\n<some-tag/>\nsuffix"
        trimmed = rasaeco.render._trim_newlines_around_tags(text=text)

        self.assertEqual(text, trimmed)

    def test_trailing_new_lines_to_trim(self) -> None:
        text = "prefix\n\n<some-tag>\n\nsay\nsomething</some-tag>\nsuffix"
        trimmed = rasaeco.render._trim_newlines_around_tags(text=text)

        self.assertEqual(
            "prefix\n\n<some-tag>say\nsomething</some-tag>\nsuffix", trimmed
        )

    def test_leading_new_lines_to_trim(self) -> None:
        text = "prefix\n\n<some-tag>say\nsomething\n\n</some-tag>\nsuffix"
        trimmed = rasaeco.render._trim_newlines_around_tags(text=text)

        self.assertEqual(
            "prefix\n\n<some-tag>say\nsomething</some-tag>\nsuffix", trimmed
        )

    def test_multi_line_tags(self) -> None:
        text = "prefix\n\n<\nsome-tag\n>\n\nsay\nsomething\n\n<\n/\nsome-tag\n>\nsuffix"
        trimmed = rasaeco.render._trim_newlines_around_tags(text=text)

        self.assertEqual(
            "prefix\n\n<\nsome-tag\n>say\nsomething<\n/\nsome-tag\n>\nsuffix", trimmed
        )

    def test_nested_tag(self) -> None:
        text = (
            "prefix\n\n"
            "<some-tag>\n\n"
            "say\n"
            "<another>\nsay\nanother\n</another>\n"
            "something\n\n"
            "</some-tag>\n"
            "suffix"
        )
        trimmed = rasaeco.render._trim_newlines_around_tags(text=text)

        expected = (
            "prefix\n\n"
            "<some-tag>say\n"
            "<another>say\nanother</another>\n"
            "something</some-tag>\n"
            "suffix"
        )
        self.assertEqual(expected, trimmed)


if __name__ == "__main__":
    unittest.main()
