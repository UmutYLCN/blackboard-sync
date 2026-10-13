# Fonts of the PDF notes

Noto Sans (Regular, Bold, Italic, Bold Italic) and Noto Sans Mono (Regular),
from <https://github.com/notofonts/notofonts.github.io> (`fonts/*/unhinted/ttf`),
licensed under the SIL Open Font License 1.1 (`OFL.txt`).

They are cut down to Latin, Turkish and Greek letters and common punctuation;
the mono font also keeps arrows, math symbols and shapes, which the PDF notes
use for characters Noto Sans lacks. fonttools is only needed to make them, in a
throwaway virtual environment outside the repository, never by the app:

```sh
U="U+0020-007E,U+00A0-017F,U+0192,U+02C6-02DC,U+0391-03C9,U+2000-206F,U+20AC,U+20BA,U+2116,U+2122,U+2212,U+FFFD"
OPTS="--layout-features= --drop-tables+=GSUB,GPOS,GDEF,DSIG --no-hinting --name-IDs=0,1,2,3,4,5,6,13,14"
for f in NotoSans-Regular NotoSans-Bold NotoSans-Italic NotoSans-BoldItalic; do
  pyftsubset "$f.ttf" --unicodes="$U" $OPTS --output-file="assets/fonts/$f.ttf"
done
pyftsubset NotoSansMono-Regular.ttf --unicodes="$U,U+2190-21FF,U+2200-22FF,U+25A0-25FF" $OPTS \
  --output-file=assets/fonts/NotoSansMono-Regular.ttf
```
