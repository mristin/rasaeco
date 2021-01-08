import unittest

import inflect

ENGINE =inflect.engine()

class TestInflect(unittest.TestCase):
    def test_on_composite_words(self)->None:
        word = 'misplaced scaffold'
        plural = ENGINE.plural_noun(word)
        self.assertEqual('misplaced scaffolds', plural)

    def test_on_composite_words_with_more_involved_ending(self)->None:
        word = 'misplaced catch'
        plural = ENGINE.plural_noun(word)
        self.assertEqual('misplaced catches', plural)

if __name__ == "__main__":
    unittest.main()
