from datetime import datetime
from pony.orm import *
import os
import unicodedata
from encode import unpack, exists
import re

db = Database()
if os.path.exists("comics.sqlite"):
    os.remove("comics.sqlite")
db.bind('sqlite', ':memory:', create_db=True)

LINK = re.compile(r"https?://\S+")
SITE = "http://www.localhost.com:8080"


def normalize(text):
    nfkd_form = unicodedata.normalize('NFKD', text.lower())
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def is_writer(value, tables):
    details = exists(tables, "gcd_credit_type", value)
    if details:
        return "script" in details[1]


def is_artist(value, tables):
    details = exists(tables, "gcd_credit_type", value)
    if details:
        return "pencils" in details[1] or "painting" in details[1]


def is_inker(value, tables):
    details = exists(tables, "gcd_credit_type", value)
    if details:
        return "inks" in details[1]


def updateStoryCredits(values, tables):
    creator = exists(tables, "gcd_creator_name_detail", values[8])
    if creator:
        creator = exists(tables, "gcd_creator", creator[3])
    story = exists(tables, "gcd_story", values[10])
    type = values[9]
    if creator and story:
        #print("VALUES:", values)
        #print("STORY (before):", story, values[10])
        modified = False
        #details = []
        if is_writer(type, tables):
            #details.append("writer")
            if not story.writer:
                story.writer = creator
                modified = True
        if is_artist(type, tables):
            #details.append("artist")
            if not story.pencils:
                story.pencils = creator
                modified = True
        if is_inker(type, tables):
            #details.append("inker")
            if not story.inks:
                story.inks = creator
                modified = True
        if modified:
            commit()
            #print("STORY (after):", story, values[10])
        #print("CREATOR:", creator, details, values[8])



def comic_date(ymd):
    """
    11 bits for year
    5 bits for month
    5 bits for day
    For month
    0 Unknown
    Month * 2
    1 New Year
    3 Valentine's
    5 Spring Special
    7 Easter Special
    9 ?
    11 ?
    13 Summer Special
    15 ?
    17 ?
    19 Fall Special
    21 Halloween Special
    23 Winter Special
    25 Christmas Special
    27 Annual
    29 Other
    So we can sort numerically
    """
    try:
        year, month, day = map(int, ymd.split("-"))
        return day + month * 32 + year * 1024
    except:
        return 0


def bold(text, terms):
    plain = normalize(text)
    if plain == text.lower():
        for term in terms:
            text = re.sub(term, f"<b>{term}</b>", text, 1, re.IGNORECASE)
        return text

    text = unicodedata.normalize("NFKD", text)

    remap = {}
    pos = 0
    for i, ch in enumerate(text):
        if not unicodedata.combining(ch):
            remap[pos] = i
            pos += 1

    matches = []
    last = 0
    for term in terms:
        match = re.search(term, plain[last:], re.IGNORECASE)
        if match:
            matches.append((remap[match.start(0) + last], remap[match.end(0) + last]))
            last = match.end(0) + 1
            # text = regex.sub(f"<b>{matches.group(0)}</b>", text, 1)
        # text = text.replace(term, f"<b>{term}</b>", 1)

    if matches:
        tokens = [ch for ch in text]
        for start, end in matches:
            tokens[start] = f"<b>{tokens[start]}"
            tokens[end] = f"{tokens[end]}</b>"
        return "".join(tokens)
    return text


class Mixin(object):

    def search(self, field, value):
        pass

    def label(self, terms):
        return bold(str(self), terms)

    @classmethod
    def fromGCD(cls, values, tables):
        pass

    @classmethod
    def prefetch(cls, selection):
        return selection

    @classmethod
    def order_by(cls, selection):
        return selection


def getByName(cls, name, **kwargs):
    ascii = normalize(name)
    obj = cls.get(ascii=ascii)
    if obj is None:
        obj = cls(name=name, ascii=ascii, **kwargs)
        commit()
    return obj


def find(model, **kwargs):
    for field in kwargs:
        search = kwargs[field]
    if len(search) == 1:
        return select(q for q in model if search[0] in getattr(q, field))
    query = f"%{'%'.join(search)}%"
    sql = f'"q"."{field}" like $query'
    return select(q for q in model if raw_sql(sql))


class Era(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    name = Required(str, unique=True)
    start_year = Required(int)
    end_year = Required(int)


class Scanner(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str)
    group = Optional('ScannerGroup')
    scans = Set('Scan')


class Scan(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    comic = Required('Comic')
    c2c = Required(bool)
    scanner = Optional(Scanner)
    pages = Set('Page')
    urls = Set('URL')
    files = Set('File')
    hash = Optional(str)
    size = Required(int)


class ScannerGroup(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str)
    scanners = Set(Scanner)


class Comic(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    scans = Set(Scan)
    date = Required(int)
    cover_date = Optional(str)
    publisher = Optional('IndiciaPublisher')
    issue = Optional(str)
    variant = Optional(str)
    volume = Optional(str)
    pages = Optional(int)
    notes = Optional(LongStr)
    isbn = Optional(str)
    barcode = Optional(str)
    title = Optional(str)
    brand = Optional('Brand')
    cover_price = Optional(str)
    series = Optional('Series')
    stories = Set('Story')
    #reprints = Set('Reprint')
    ratings = Set('Rating')
    reading_list_entrys = Set('ReadingListEntry')
    historys = Set('History')

    @classmethod
    def prefetch(cls, selection):
        return selection.prefetch(Comic.notes)

    @classmethod
    def order_by(cls, selection):
        return selection.order_by(lambda comic: (comic.series.name, comic.date))

    @classmethod
    def fromGCD(cls, values, tables):
        date = comic_date(values[11])
        series = exists(tables, "gcd_series", values[5])  # Series.get(id=values[5])
        brand = exists(tables, "gcd_brand", values[8])  # Brand[values[8]]
        publisher = exists(tables, "gcd_indicia_publisher", values[12])
        if series:
            series = series.id
        if brand:
            brand = brand.id
        if publisher:
            publisher = publisher.id
        if values[14]:
            pages = int(values[14])
        else:
            pages = None

        comic = Comic(issue=values[1], volume=values[2], series=series, brand=brand,
                      cover_date=values[10], date=date, publisher=publisher, variant=values[27],
                      cover_price=values[13], pages=pages, notes=values[20],
                      isbn=values[24], barcode=values[28], title=values[30])
        commit()
        # print(values)
        # print(comic, comic.issue, comic.series, comic.brand, comic.cover_date, comic.cover_price,
        #      comic.pages, comic.notes)
        return comic

    @property
    def display_date(self):
        return IntDate(self, "date")

    @property
    def html_notes(self):
        notes = self.notes
        notes = notes.replace(r"\r\n\r\n", r"\r\n")
        notes = notes.replace(r"\r\n", "<br/>")
        urls = LINK.findall(notes)
        for url in urls:
            notes = notes.replace(url, f'<a href="{url}" target="_blank">{url}</a>')
        return notes

    @property
    def thumb(self):
        for scan in self.scans:
            thumb = os.path.join("static", "thumbs", f"{scan.id}.jpg")
            if os.path.exists(thumb):
                return f'<a href="/view/{scan.id}"><img src="/static/thumbs/{scan.id}.jpg" class="w-100" /></a>'

        return '<img src="/static/images/missing.jpg" class="w-100" />'

    def thumb_api_link(self):
        for scan in self.scans:
            thumb = os.path.join("static", "thumbs", f"{scan.id}.jpg")
            if os.path.exists(thumb):
                return f"{SITE}/static/thumbs/{scan.id}.jpg"

    def view_api_link(self):
        for scan in self.scans:
            thumb = os.path.join("static", "thumbs", f"{scan.id}.jpg")
            if os.path.exists(thumb):
                return f"{SITE}/api/view/{scan.id}"

    @property
    def series_name(self):
        if self.series:
            return self.series.name
        else:
            return "None"


class IntDate():

    def __init__(self, model, field):
        self.model = model
        self.field = field
        ymd = getattr(model, field)
        y = int(ymd // 1024)
        m = int(ymd // 64) & 15
        d = ymd & 31

        if ymd < 0:
            self.date = "New Scan"
        elif d:
            self.date = f"{y:04}/{m:02}/{d:02}"
        elif m:
            self.date = f"{y:04}/{m:02}"
        elif y:
            self.date = f"{y:04}"
        else:
            self.date = "?"

        """        
        11 bits for year
        5 bits for month
        5 bits for day
        For month
        0 Unknown
        Month * 2
        1 New Year
        3 Valentine's
        5 Spring Special
        7 Easter Special
        9 ?
        11 ?
        13 Summer Special
        15 ?
        17 ?
        19 Fall Special
        21 Halloween Special
        23 Winter Special
        25 Christmas Special
        27 Annual
        29 Other
        So we can sort numerically
        """

    def __str__(self):
        return self.date


class Brand(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str)
    notes = Optional(LongStr)
    comics = Set(Comic)

    @classmethod
    def fromGCD(cls, values, tables):
        brand = getByName(Brand, values[1], notes=values[4])
        return brand

    def __str__(self):
        return self.name


class Publisher(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str, unique=True)
    start_year = Optional(int)
    end_year = Optional(int)
    notes = Optional(LongStr)
    series = Set('Series')
    indicias = Set("IndiciaPublisher")

    @classmethod
    def fromGCD(cls, values, tables):
        publisher = getByName(Publisher, values[1], start_year=values[3], end_year=values[4], notes=values[5])
        return publisher

    def __str__(self):
        return self.name

    def label(self, terms):
        return f"{bold(self.name, terms)} <i>({self.start_year}-{self.end_year})</i>"


class IndiciaPublisher(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str, unique=True)
    parent = Optional(Publisher)
    start_year = Optional(int)
    end_year = Optional(int)
    notes = Optional(LongStr)
    comics = Set(Comic)

    @classmethod
    def fromGCD(cls, values, tables):
        publisher = exists(tables, "gcd_publisher", values[2])
        if publisher:
            publisher = publisher.id
        indiciaPublisher = getByName(IndiciaPublisher, values[1], parent=publisher,
                                     start_year=values[4], end_year=values[5], notes=values[7])
        return indiciaPublisher

    def label(self, terms):
        return f"{bold(self.name, terms)} <i>({self.parent} {self.start_year}-{self.end_year})</i>"


class Series(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    comics = Set(Comic)
    name = Required(str)
    start_year = Optional(int)
    end_year = Optional(int)
    publisher = Optional(Publisher)
    notes = Optional(LongStr)

    @classmethod
    def fromGCD(cls, values, tables):
        publisher = exists(tables, "gcd_publisher", values[12])
        if publisher:
            publisher = publisher.id
        series = Series(name=values[1], start_year=values[4], end_year=values[6],
                        publisher=publisher, notes=values[16])
        commit()
        return series

    @classmethod
    def find(cls, search: [str, ...]):
        return find(Series, name=search)

    def __str__(self):
        return f"{self.name} ({self.publisher} {self.start_year}-{self.end_year})"

    def label(self, terms):
        return f"{bold(self.name, terms)} <i>({self.publisher} {self.start_year}-{self.end_year})</i>"


class StoryType(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    type = Required(str)
    sort_type = Required(int)
    stories = Set('Story')


    def __str__(self):
        return self.type
    @classmethod
    def fromGCD(cls, values, tables):
        return StoryType(type=values[1], sort_type=values[2])


class FeatureType(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    type = Required(str)
    features = Set('Feature')

    @classmethod
    def fromGCD(cls, values, tables):
        return FeatureType(type=values[1])


class Page(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    index = Required(int)
    filename = Required(str)
    hash = Optional(str)
    width = Optional(int)
    height = Optional(int)
    page_type = Required('PageType')
    ocr = Optional(LongStr)
    scan = Required(Scan)


class PageType(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str, unique=True)
    pages = Set(Page)


class Story(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    title = Optional(str)
    feature = Optional(str)
    sequence = Optional(int)
    page_count = Optional(int)
    type = Optional(StoryType)
    writer = Optional('Creator')
    pencils = Optional('Creator')
    inks = Optional('Creator')
    genres = Set('Genre')
    #characters = Set('Character')
    groupCharacters = Set('GroupCharacter')
    synopsis = Optional(LongStr)
    notes = Optional(LongStr)
    comic = Optional(Comic)
    next_part = Optional('Story', reverse='previous_part')
    previous_part = Optional('Story', reverse='next_part')
    see_also = Set('Story', reverse='see_also')
    storyCharacters = Set("StoryCharacter")

    def __str__(self):
        return f"{self.title} ({self.type}) Writer:{self.writer} Pencils:{self.pencils} Inks:{self.inks}"

    @classmethod
    def fromGCD(cls, values, tables):
        page_count = values[5]
        if page_count is not None:
            page_count = int(page_count)
        writer = Creator.add(values[7])
        pencils = Creator.add(values[8])
        inks = Creator.add(values[9])
        type = exists(tables, "gcd_story_type", values[5])
        if type:
            type = type.id

        comic = exists(tables, "gcd_issue", values[6])
        if comic:
            comic = comic.id

        story = Story(title=values[1], feature=values[3], sequence=values[4], type=type,
                      page_count=page_count, writer=writer, pencils=pencils, comic=comic,
                      inks=inks, synopsis=values[15], notes=values[17])
        commit()

        genres = values[13]
        characters = values[14]
        Genre.add(genres, story)
        #Character.add(characters, story)
        # print(f"[{story.id}] {story.title} Writer:{story.writer} Pencils:{story.pencils} Inks:{story.inks}")
        # print(genres, characters)
        return story


class Creator(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str)
    writers = Set(Story, reverse="writer")
    pencils = Set(Story, reverse="pencils")
    inks = Set(Story, reverse="inks")
    notes = Optional(LongStr)


    def __str__(self):
        return f"{self.name} [{self.notes}]"

    @classmethod
    def fromGCD(cls, values, tables):
        if values[13] and values[14]:
            notes = f"{values[13]} {values[14]}"
        else:
            notes = values[13] or values[14]
        creator = getByName(Creator, values[1], notes=notes)
        return creator

    @classmethod
    def add(cls, names):
        for name in names.split(";"):
            ascii = normalize(name.strip())
            if ascii:
                creator = Creator.get(ascii=ascii)
                if creator:
                    return creator.id

    def label(self, terms):
        return bold(self.name, terms)
        # Too slow, need to add bit field for roles
        roles = []
        if len(self.writers):
            roles.append("Writer")
        if len(self.pencils):
            roles.append("Pencils")
        if len(self.inks):
            roles.append("Inks")
        return f"{bold(self.name, terms)} <i>({','.join(roles)})</i>"


class Genre(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str)
    stories = Set(Story)
    features = Set("Feature")

    @classmethod
    def add(cls, names, story):
        for name in names.split(";"):
            name = name.strip()
            if name:
                genre = getByName(Genre, name)
                genre.stories.add(story)

    @classmethod
    def addFeature(cls, names, feature):
        for name in names.split(";"):
            name = name.strip()
            if name:
                genre = getByName(Genre, name)
                genre.features.add(feature)

"""
class Character(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str)
    notes = Optional(LongStr)
    aka = Optional(str)
    stories = Set(Story)

    @classmethod
    def add(cls, names, story):
        for name in names.split(";"):
            name = name.strip()
            if "(" in name:
                name = name.split("(")[0].strip()
            if "[" in name:
                name = name.split("[")[0].strip()
            if name:
                character = getByName(Character, name)
                character.stories.add(story)

    def label(self, terms):
        if self.aka:
            return f"{bold(self.name, terms)} aka {self.aka}"
        return bold(self.name, terms)
"""


class RelationType(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    type = Required(str)
    reverse_type = Required(str)
    characterRelations = Set("CharacterRelation")
    groupRelations = Set("GroupRelation")

    @classmethod
    def fromGCD(cls, values, tables):
        type = values[1]
        reverse_type = values[2]
        return RelationType(type=type, reverse_type=reverse_type)



class CharacterRelation(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    notes = Optional(LongStr)
    from_character = Optional("CharacterDetails", reverse="from_character")
    to_character = Optional("CharacterDetails", reverse="to_character")
    relation_type = Optional(RelationType)

    @classmethod
    def fromGCD(cls, values, tables):
        from_character = exists(tables, "gcd_character", values[2])
        if from_character:
            from_character = from_character.id
        to_character = exists(tables, "gcd_character", values[4])
        if to_character:
            to_character = to_character.id
        relation_type = exists(tables, "gcd_character_relation_type", values[3])
        if relation_type:
            relation_type = relation_type.id

        return CharacterRelation(notes=values[1], from_character=from_character,
                                 to_character=to_character, relation_type=relation_type)



class GroupRelation(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    notes = Optional(LongStr)
    from_group = Optional("Group", reverse="from_group")
    to_group = Optional("Group", reverse="to_group")
    relation_type = Optional(RelationType)

    @classmethod
    def fromGCD(cls, values, tables):
        from_group = exists(tables, "gcd_group", values[2])
        if from_group:
            from_group = from_group.id
        to_group = exists(tables, "gcd_group", values[4])
        if to_group:
            to_group = to_group.id
        relation_type = exists(tables, "gcd_group_relation_type", values[3])
        if relation_type:
            relation_type = relation_type.id

        return GroupRelation(notes=values[1], from_group=from_group,
                                 to_group=to_group, relation_type=relation_type)

class CharacterName(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str)
    sort_name = Required(str)
    character = Optional('CharacterDetails')
    is_official = Required(bool)
    stories = Set("StoryCharacter")

    @classmethod
    def fromGCD(cls, values, tables):
        name = values[2]
        ascii = normalize(name)
        character = exists(tables, "gcd_character", values[4])
        if character:
            character = character.id
        characterName = CharacterName(ascii=ascii, name=name, sort_name=values[3], character=character,
                                      is_official=values[5])
        return characterName


class CharacterDetails(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str, index=True)
    name = Required(str)
    sort_name = Required(str)
    disambiguation = Optional(str)
    year_first_published = Optional(int)
    description = Optional(str)
    notes = Optional(str)
    universe = Optional('Universe')
    aka = Set('CharacterName')
    from_character = Set("CharacterRelation")
    to_character = Set("CharacterRelation")
    memberOf = Set("GroupMembership")

    @classmethod
    def fromGCD(cls, values, tables):
        name = values[2]
        ascii = normalize(name)
        universe = exists(tables, "gcd_universe", values[10])
        if universe:
            universe = universe.id
        characterDetails = CharacterDetails(ascii=ascii, name=name, sort_name=values[3],
                                            disambiguation=values[4], year_first_published=values[5],
                                            description=values[7], notes=values[8], universe=universe)
        return characterDetails


class Universe(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    name = Optional(str)
    designation = Optional(str)
    year_first_published = Optional(int)
    description = Optional(str)
    notes = Optional(str)
    multiverse = Optional("Multiverse")
    characters = Set(CharacterDetails)
    groups = Set("Group")
    groupCharacters = Set("GroupCharacter")
    storyCharacters = Set("StoryCharacter")

    @classmethod
    def fromGCD(cls, values, tables):
        name = values[3]
        multiverse = exists(tables, "gcd_multiverse", values[9])
        if multiverse:
            multiverse = multiverse.id
        universe = Universe(name=name, designation=values[4],
                            year_first_published=values[5], description=values[7],
                            notes=values[8], multiverse=multiverse)
        return universe


class Multiverse(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    name = Required(str)
    universes = Set(Universe)

    @classmethod
    def fromGCD(cls, values, tables):
        name = values[2]
        return Multiverse(name=name)


class Group(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    ascii = Required(str)
    name = Required(str)
    sort_name = Required(str)
    disambiguation = Optional(str)
    year_first_published = Optional(int)
    description = Optional(LongStr)
    notes = Optional(LongStr)
    universe = Optional(Universe)
    members = Set("GroupCharacter")
    from_group = Set("GroupRelation")
    to_group = Set("GroupRelation")
    groupMembers = Set("GroupMembership")
    stories = Set("StoryCharacterGroup")


    @classmethod
    def fromGCD(cls, values, tables):
        name = values[2]
        ascii = normalize(name)
        universe = exists(tables, "gcd_universe", values[10])
        if universe:
            universe = universe.id
        return Group(ascii=ascii, name=name, sort_name=values[3], disambiguation=values[4],
                     year_first_published=values[5], description=values[7],
                     notes=values[8], universe=universe)



class GroupCharacter(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    notes = Optional(str)
    group = Optional(Group)
    story = Optional(Story)
    universe = Optional(Universe)

    @classmethod
    def fromGCD(cls, values, tables):
        notes = values[2]
        group = exists(tables, "gcd_group", values[3])
        if group:
            group = group.id
        else:
            groupName = exists(tables, "gcd_group_name_detail", values[6])
            if groupName:
                group = exists(tables, "gcd_group", groupName[-1])
                if group:
                    group = group.id

        universe = exists(tables, "gcd_universe", values[5])
        if universe:
            universe = universe.id
        story = exists(tables, "gcd_story", values[4])
        return GroupCharacter(notes=notes, group=group, story=story, universe=universe)


class Role(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    name = Required(str)
    stories = Set("StoryCharacter")

    @classmethod
    def fromGCD(cls, values, tables):
        return Role(name=values[1])


class GroupMembershipType(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    type = Required(str)
    members = Set("GroupMembership")

    @classmethod
    def fromGCD(cls, values, tables):
        return GroupMembershipType(type=values[1])


class GroupMembership(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    year_joined = Optional(int)
    year_left = Optional(int)
    notes = Optional(LongStr)
    character = Optional(CharacterDetails)
    group = Optional(Group)
    membershipType = Optional(GroupMembershipType)

    @classmethod
    def fromGCD(cls, values, tables):
        character = exists(tables, "gcd_character", values[6])
        group = exists(tables, "gcd_group", values[7])
        membershipType = exists(tables, "gcd_group_membership_type", values[8])
        return GroupMembership(year_joined=values[1], year_left=values[3], notes=values[5],
                               character=character, group=group, membershipType=membershipType)


class StoryCharacter(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    is_flashback = Required(bool)
    is_origin = Required(bool)
    is_death = Required(bool)
    notes = Optional(str)
    character = Optional(CharacterName)
    role = Optional("Role")
    story = Optional(Story)
    universe = Optional(Universe)
    groups = Set("StoryCharacterGroup")


    @classmethod
    def fromGCD(cls, values, tables):
        notes = values[5]
        character = exists(tables, "gcd_character_name_detail", values[6])
        if character:
            character = character.id
        role = exists(tables, "gcd_character_role", values[7])
        if role:
            role = role.id
        story = exists(tables, "gcd_story", values[8])
        universe = exists(tables, "gcd_universe", values[9])
        if universe:
            universe = universe.id
        return StoryCharacter(is_flashback=values[2], is_origin=values[3], is_death=values[4],
                              notes=notes, character=character, role=role, story=story, universe=universe)



class StoryCharacterGroup(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    story_character = Optional(StoryCharacter)
    group = Optional(Group)

    @classmethod
    def fromGCD(cls, values, tables):
        story_character = exists(tables, "gcd_story_character", values[1])
        group = exists(tables, "gcd_group", values[2])
        return StoryCharacterGroup(story_character=story_character, group=group
                                   )

class Feature(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    name = Optional(str)
    notes = Optional(LongStr)
    type = Optional(FeatureType)
    disambiguation = Optional(str)
    genres = Set(Genre)

    @classmethod
    def fromGCD(cls, values, tables):
        type = exists(tables, "gcd_feature_type", values[8])
        feature = Feature(name=values[2], notes=values[7], type=type, disambiguation=values[10])
        commit()
        genres = values[4]
        Genre.addFeature(genres, feature)
        return feature


class URL(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    url = Optional(str)
    scan = Optional(Scan)


class File(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    path = Optional(str, unique=True)
    scan = Required(Scan)

"""
class Reprint(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    comics = Set(Comic)
"""


class User(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    name = Required(str)
    ascii = Required(str, index=True)
    password = Required(str)  # Hash of password
    role = Optional(int, default=3)
    # 1 Super
    # 2 Admin
    # 3 Regular
    email = Required(str, unique=True)
    ratings = Set('Rating')
    historys = Set('History')


class Rating(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    rating = Required(int)
    user = Required(User)
    comic = Required(Comic)


class ReadingList(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    name = Required(str)
    ascii = Required(str)
    reading_list_entrys = Set('ReadingListEntry')
    historys = Set('History')


class ReadingListEntry(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    index = Required(float)
    reading_list = Required(ReadingList)
    comic = Required(Comic)


class History(db.Entity, Mixin):
    id = PrimaryKey(int, auto=True)
    comics = Optional(Comic)
    user = Required(User)
    date = Required(datetime)
    reading_list = Optional(ReadingList)
    index = Optional(float)  # Index for reading list


db.generate_mapping(create_tables=True)
# db.generate_mapping()
