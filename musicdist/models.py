from datetime import date
from typing import Annotated, Literal
import re
import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1, max_length=250)]
ID = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')]
DESTINATIONS = ['apple_music', 'spotify', 'amazon_music', 'youtube_music', 'tidal', 'deezer']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Credit(StrictModel):
    name: Text
    role: Literal['composer', 'lyricist', 'producer', 'performer']

class Track(StrictModel):
    id: ID
    title: Text
    artist: Text
    isrc: str
    explicit: bool
    instrumental: bool = False
    language: str = 'en'
    credits: list[Credit] = Field(min_length=1)
    master: str | None = None  # CLI only; API refuses local filesystem paths.
    asset_id: ID | None = None

    @field_validator('isrc')
    @classmethod
    def isrc_valid(cls, value):
        value = value.replace('-', '').upper()
        if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{3}\d{7}', value):
            raise ValueError('ISRC must contain country, registrant, year and designation: 12 characters')
        return value

    @field_validator('language')
    @classmethod
    def language_valid(cls, value):
        if value != 'zxx' and pycountry.languages.get(alpha_2=value) is None and pycountry.languages.get(alpha_3=value) is None:
            raise ValueError('Use a valid ISO language code, or zxx for no linguistic content')
        return value

    @model_validator(mode='after')
    def authors(self):
        roles = {c.role for c in self.credits}
        if 'composer' not in roles or (not self.instrumental and 'lyricist' not in roles):
            raise ValueError('Composer credit required; vocal tracks also require lyricist credit')
        return self

class Release(StrictModel):
    id: ID
    artist_id: ID
    title: Text
    artist: Text
    label: Text
    upc: str
    release_date: date
    original_release_date: date | None = None
    genre: Text
    copyright_line: Text
    phonographic_copyright_line: Text
    rights_confirmed: bool = False
    territories: list[str] = Field(default_factory=lambda: ['Worldwide'], min_length=1)
    destinations: list[str] = Field(min_length=1)
    artwork: str | None = None  # CLI only
    artwork_asset_id: ID | None = None
    tracks: list[Track] = Field(min_length=1, max_length=200)

    @field_validator('upc')
    @classmethod
    def barcode(cls, value):
        if not re.fullmatch(r'\d{12,13}', value):
            raise ValueError('UPC/EAN must be 12 or 13 digits, kept as text')
        total = sum(int(n) * (3 if i % 2 == 0 else 1) for i, n in enumerate(reversed(value[:-1])))
        if (10 - total % 10) % 10 != int(value[-1]):
            raise ValueError('Invalid UPC/EAN check digit; use an assigned code')
        return value

    @field_validator('destinations')
    @classmethod
    def destinations_valid(cls, values):
        if len(values) != len(set(values)) or set(values) - set(DESTINATIONS):
            raise ValueError('Select unique destinations from the supported planning list')
        return values

    @field_validator('territories')
    @classmethod
    def territories_valid(cls, values):
        if values == ['Worldwide']:
            return values
        if len(set(values)) != len(values) or any(pycountry.countries.get(alpha_2=v) is None for v in values):
            raise ValueError('Use Worldwide alone or unique ISO two-letter country codes')
        return values

    @model_validator(mode='after')
    def unique_tracks(self):
        if len({t.id for t in self.tracks}) != len(self.tracks) or len({t.isrc for t in self.tracks}) != len(self.tracks):
            raise ValueError('Track IDs and ISRCs must be unique within this release')
        if self.original_release_date and self.original_release_date > self.release_date:
            raise ValueError('Original release date cannot follow release date')
        return self
