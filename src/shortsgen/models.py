from pydantic import BaseModel


class Word(BaseModel):
    start: float
    end: float
    text: str


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[Word] = []


class Transcript(BaseModel):
    language: str
    segments: list[TranscriptSegment]

    def words_between(self, start: float, end: float) -> list[Word]:
        words: list[Word] = []
        for seg in self.segments:
            for w in seg.words:
                if w.start >= start and w.end <= end:
                    words.append(w)
        return words


class Highlight(BaseModel):
    start: float
    end: float
    title: str
    reason: str
    description: str
    tags: list[str]
    hashtags: list[str]
    category: str
    quality_score: int


class HighlightList(BaseModel):
    highlights: list[Highlight]
