"""Step 5: an original is put in only if every part of it is in the source."""

from translator import sources


SOURCE = ["ועשית כל מלאכתך. כשתבא שבת יהא בעיניך כאלו כל מלאכתך עשויה, שלא תהרהר אחר מלאכה (שם):"]


def test_verify():
    assert sources.verify("כאלו כל מלאכתך עשויה", SOURCE) == []
    assert sources.verify("כשתבא שבת … כאלו כל מלאכתך עשויה", SOURCE) == []           # a skip marked with …
    assert sources.verify("יהא [לך] בעיניך", SOURCE) == []                             # Polen's addition in [ ]
    assert sources.verify("כאילו כל מלאכתך עשויה", SOURCE) == ["כאילו כל מלאכתך עשויה"]  # plene spelling is not the source
    assert sources.verify("שלא תהרהר … כשתבא שבת", SOURCE) == ["כשתבא שבת"]            # parts must come in order


def test_clean_and_norm():
    assert sources.clean("<b>זָכוֹר</b> אֶת־יוֹם") == "זכור את־יום"
    assert sources.norm('"כְּאִלּוּ", כל') == "כאלו כל"
