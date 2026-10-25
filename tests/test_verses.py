"""The Sefaria verse check: cleaning Sefaria's text, matching by letters, and what may be corrected."""

from translator import verses


def test_clean_verse():
    raw = ('אָ֗ז תִּתְעַנַּג֙ עַל־יְהֹוָ֔ה וְהִרְכַּבְתִּ֖יךָ עַל־<span class="mam-kq"><span class="mam-kq-q">[בָּ֣מֳתֵי]</span> '
           '<span class="mam-kq-k">(במותי)</span></span> אָ֑רֶץ י֥וֹם&thinsp;<small>׀</small>&thinsp;יֽוֹם׃')
    assert verses.clean_verse(raw) == "אָז תִּתְעַנַּג עַל־ה' וְהִרְכַּבְתִּיךָ עַל־בָּמֳתֵי אָרֶץ יוֹם יוֹם"
    assert verses.clean_verse("וְכׇל־צְבָאָֽם׃") == "וְכָל־צְבָאָם"                  # qamats qatan, meteg, sof pasuq


def test_find():
    vs = [("Exodus 16:30", "וַיִּשְׁבְּתוּ הָעָם בַּיּוֹם הַשְּׁבִעִי"), ("Genesis 1:31", "וְהִנֵּה־טוֹב מְאֹד")]
    assert verses.find(["טוֹב", "מְאֹד"], vs)[0] == "exact"
    assert verses.find(["טוֹב", "מָאֹד"], vs)[:2] == ("vowels", "Genesis 1:31")
    assert verses.find(["בַּיּוֹם", "הַשְּׁבִיעִי"], vs) is None                    # plene spelling: not by letters
    assert verses.find(["בַּיּוֹם", "הַשְּׁבִיעִי"], vs, key=verses.loose)[1] == "Exodus 16:30"
    assert verses.find(["הִנֵּה", "טוֹב"], vs, key=verses.loose) is None             # a missing leading ו is not spelling


def test_split_prefix():
    assert list(verses.split_prefix("ברוּחַ"))[0] == ("ב", "רוּחַ")
    assert list(verses.split_prefix("הַיּוֹם")) == []                              # ה with its own vowel stays
    assert verses.references("as in Gen. 2:1 and II Samuel 7:10; Ex 16:29") == [
        ("Exodus", 16), ("Genesis", 2), ("II Samuel", 7)]


def test_vocalise_helpers():
    runs = verses._plain_runs('כה אמר ה\' השמרו בנפשותיכם, וגם "השמים והארץ\'')
    assert runs[0][2][:3] == ["כה", "אמר", "ה'"]                                  # ה' is one word
    assert all(not w.endswith("'") or len(w) <= 3 for _, _, ws in runs for w in ws)  # a closing quote is not a geresh
    vs = [("Jeremiah 17:21", "כֹּה אָמַר ה' הִשָּׁמְרוּ בְּנַפְשׁוֹתֵיכֶם וְאַל־תִּשְׂאוּ מַשָּׂא")]
    n, ref, piece = verses._longest_match(["כה", "אמר", "ה'", "השמרו", "בנפשותיכם", "ואל", "תשאו"], vs)
    assert (n, ref) == (7, "Jeremiah 17:21") and piece.endswith("וְאַל־תִּשְׂאוּ") and "ה'" in piece
    assert verses.nfc("לִָם".replace("ִָ", "ָ͏ִ")) == verses.nfc("לִָם")         # the joiner never splits equal pointing
