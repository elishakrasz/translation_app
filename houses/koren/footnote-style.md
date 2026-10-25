# Koren house profile — footnote style

*The house default for every Koren / Maggid book. Written for the Rosen translation (decisions of 1 Oct 2026) and moved into the engine on 25 Oct 2026. A book overrides a rule in its project.yaml (`policies`) or style sheet, and says so.*

**House decisions (1 Oct 2026):** (1) system **A**: Koren short forms in the notes plus a רשימת קיצורים ביבליוגרפיים at the end of the book; (2) numbered sections are written **סי'**; (3) Hebrew works that the English cites in translation or transliteration are cited **by their Hebrew title**. Foreign-language works stay in their original language and script.

**Basis.** Koren does not publish a style guide. The model is Koren's own practice in a current scholarly Hebrew book from its Maggid imprint: Yonatan Grossman, *מגילת רות: גשרים וגבולות* (ספרי מגיד, הוצאת קורן, תשפ"ו 2026). The 85-page sample is in `~/translation_app/library/house-samples/koren/` (not in git: copyrighted). Where that sample doesn't show a case, the rule follows the published author guidelines of the two Jerusalem presses that set the norm for Hebrew Jewish-studies books: Yad Ben-Zvi and the Zalman Shazar Center . The one deliberate departure, at the translator's request, is that works in English and other languages stay in their original language.

Source of each rule: **K** = seen in the Koren/Maggid book · **J** = Yad Ben-Zvi / Shazar guidelines · **D** = our decision.

## 1. Placement and numbering

| Rule | Source |
|---|---|
| Real footnotes at the foot of the page, numbered afresh in each chapter. In the note itself the number is followed by a full stop ("8."). | K, J |
| The superscript number comes **after** the punctuation mark or closing quotation mark: …כולו.⁸ / …דוד".⁹. If the punctuation is a dash, the number comes before it. | K, J |
| The number for a quotation goes at the end of the quotation, not after the words that introduce it. | J |
| No footnotes on headings. | J |

## 2. Wording inside the notes

| English | Hebrew | Source |
|---|---|---|
| See | **ראו:** (with a colon) | K, J |
| Cf. | **השוו:** | J |
| See also | **ראו עוד:** / ראו גם: | K |
| Ibid. | **שם** (Ibid., 82 → שם, עמ' 82) | J |
| n., nn. | **הערה, הערות** | J |
| p., pp. | **עמ'** (for one page and for several) | K, J |
| esp. | **במיוחד** (never in Latin) | J |
| A note ending in Latin script takes **no full stop**. | | J |

## 3. Hebrew books and articles (and Hebrew works the English cites in transliteration)

**Two systems are possible. Koren uses A.**

**A. Short form plus a bibliography list (Koren):** a note cites *author's surname, one or two key words of the title, page*. The full details go in a **רשימת קיצורים ביבליוגרפיים** at the end of the book.
> Koren: קויפמן, תולדות האמונה ב, עמ' 211 · ראו: וולאס, מגמה; וורתוויין, רות, עמ' 6-5

**B. Full citation at the first mention in each chapter, short form after that** (Shazar's method 2). Not used by Koren.

Full entry, whether in the bibliography (A) or at first mention (B):

| Type | Pattern | Example |
|---|---|---|
| Book | initials of first name, surname, title, place and Hebrew year | א"ז אשכולי, *החסידות בפולין*, בעריכת ד' אסף, ירושלים תשנ"ט |
| Article | initials, surname, 'title' in single quotes, journal, volume (year), pages | ר' ש"ץ־אופנהיימר, 'תורת הצדיק אצל ר' אלימלך מליז'נסק', מולד, יח (תש"כ), עמ' 378–365 |
| Volume and page | volume in Hebrew letters without geresh, then עמ' | וילנסקי, חסידים ומתנגדים, ב, עמ' 357 (not ב:357) |
| Place and year | Hebrew place name and Hebrew year, no publisher, no parentheses | ירושלים תש"ל (not "(ירושלים: 1970)") |

Hebrew books and articles that the English cites in English translation, or with a transliterated title, are cited **by their Hebrew title** (D, J: "if a work exists in Hebrew, the Hebrew version is preferred"). Schatz-Uffenheimer's article above is an example.

## 4. Works in English and other languages: original language (D)

These are cited **entirely in their own language and script, left to right**: author, *title* in italics, place and year, p./pp. No Hebrew words are mixed into the citation, because mixed-direction lines come out garbled. The publisher is dropped, following J.

| Now (mixed) | Proposed |
|---|---|
| משה אידל, Hasidism: Ecstasy and Magic (Albany: Suny Press, 1995) | M. Idel, *Hasidism: Ecstasy and Magic*, Albany 1995 |
| רחל אליאור, "Between Yesh and Ayin…". בתוך Jewish History… (London, 1988) | R. Elior, 'Between Yesh and Ayin: The Doctrine of the Zaddik in the Works of Jacob Isaac, the Seer of Lublin', in *Jewish History: Essays in Honor of Chimen Abramsky*, London 1988, pp. 393–455  |
| מרטין בובר, Tales of the Hasidim, Later Masters, בתרגום א' מרקס (ניו יורק, 1964), 245 | M. Buber, *Tales of the Hasidim: Later Masters*, trans. O. Marx, New York 1964, p. 245 |

The Hebrew text around the citation stays Hebrew: ראו: M. Idel, *Hasidism…*, Albany 1995, pp. 45–60; ועוד…

Under system A, a foreign work's short form is also in its own language: Idel, *Hasidism*, p. 45. (Koren itself writes foreign authors' short forms in Hebrew transliteration, e.g. דרייבר, מבוא. This is the one place where we knowingly depart from Koren, as the translator asked.)

## 5. Bible, Talmud and Midrash

| English | Hebrew | Source |
|---|---|---|
| Ps 63:2–3 | **תהלים ס"ג, ב–ג** (chapter with geresh/gershayim, comma, verse) | K (Koren writes "רות א', א"; Yad Ben-Zvi writes letters without geresh) |
| b. Berakhot 5b | **בבלי, ברכות ה ע"ב** | K, J |
| y. Berakhot 2:3 | ירושלמי, ברכות ב, ג (+ folio) | J |
| Gen. Rabbah 65:16 | **בראשית רבה סה, טז** (with the edition when relevant) | K ("רות רבה פרשה ב, יד"), J |
| Rashi on Ruth 3:9 | **רש"י על רות ג', ט** | K |

Book names of the Bible are never abbreviated (J).

## 6. Hasidic and rabbinic works

| English (as in Rosen's notes) | Hebrew | Note |
|---|---|---|
| Or le-Shamayim, par. Vayera, 30b | **אור לשמים, פרשת וירא, ל ע"ב** | folios as ע"א / ע"ב with a Hebrew number |
| Siah Sarfei Kodesh, 4:67, §17 | **שיח שרפי קודש, ד, עמ' 67, סי' 17** | volume letter, page, numbered section |
| Torat ha-Yehudi, 238, §30 | **תורת היהודי, עמ' 238, סי' 30** | |
| Kol Simhah, Masei, 103 | **קול שמחה, פרשת מסעי, עמ' 103** | |
| Ma'amarei Simhah, no. 30 | **מאמרי שמחה, סי' 30** | |
| Sefat Emet, par. Bamidbar, 5639 | **שפת אמת, פרשת במדבר, תרל"ט** | Hebrew year as printed |

Numbered sections are written **סי'** (§ is not used), consistently.

## 7. References within the book

- "See above, ch. 1, n. 5": system A gives the short form again (אליאור, בין יש לאין, עמ' 410), because Yad Ben-Zvi forbids "לעיל, הערה". System B gives the short form plus (לעיל, פרק 1, הערה 5).
- "See below, chapter 12": **ראו להלן, פרק 12** (unchanged).

## 8. Numbers and dates

- Page ranges are written in full, with an en dash: עמ' 378–365 (J). Koren itself writes עמ' 32-10.
- Hebrew books take the Hebrew year. Foreign books take the civil year.
