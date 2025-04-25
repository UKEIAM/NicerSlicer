import base64
import json
import zlib
from typing import Optional, List, Tuple, Literal
from enum import Enum

# from unstructured.documents.elements import CompositeElement


class SectionSate(Enum):
    # defines if the slider range is within section boundaries
    NO_SPANS = 0
    START_SPAN = 1
    END_SPAN = 2
    START_AND_END_SPANS = 3


class Section:
    """
    Class to handle the formatting of sections with bound markers
    """
    # BEGIN_MARKER = "<span class='bracket-font'>:blue-background[:blue[:material/text_select_move_forward_character:]]</span>"
    # END_MARKER = "<span class='bracket-font'>:blue-background[:blue[:material/text_select_move_back_character:]]</span>"
    # BEGIN_MARKER = "<span class='bracket-font'>:red-background[:red[\[]]</span>"
    # END_MARKER = "<span class='bracket-font'>:red-background[:red[\]]]</span>"
    BEGIN_MARKER = "<span class='bracket-font'>:red[\[]</span>"
    END_MARKER = "<span class='bracket-font'>:red[\]]</span>"
    OPEN_BRACKET = ""
    CLOSED_BRACKET = ""
    NEWLINE_TOKEN = "<$NEWLINE$>"

    def __init__(self, id_: int, text: str, title: Optional[str] = None, spans: Tuple[int, int] = (0, 0), discarded: bool = False):
        self.id_ = id_
        self.text = text
        self.spans = spans
        self.title = title
        self.discarded = discarded
        self.tokens = self._split_text_with_linebreaks(text)

    def _split_text_with_linebreaks(self, text: str) -> List[str]:
        """Split text by newlines and spaces while preserving line breaks"""
        tokens: List[str] = []
        for line in text.split("\n\n"):
            if line.split():  # ignore empty lines
                tokens += line.split(" ")
                tokens.append(self.NEWLINE_TOKEN)
        if tokens and tokens[-1] == self.NEWLINE_TOKEN:
            tokens.pop()  # remove trailing newline token
        return tokens

    def join_tokens(self, start: Optional[int] = None, end: Optional[int] = None) -> str:
        """Join tokens back to text with proper spacing and line breaks"""
        start = start if start is not None else 0
        end = end if end is not None else len(self.tokens)

        result = []
        for token in self.tokens[start:end]:
            if token == self.NEWLINE_TOKEN:
                result.append("\n\n")
            else:
                result.append(token + " ")
        return "".join(result).rstrip()

    def _slice_text(self, start: int, end: int):
        """Get text slice relative to section bounds"""
        rel_start = max(0, start - self.spans[0])
        rel_end = min(len(self.tokens), end - self.spans[0])
        # return " ".join(self.tokens[rel_start:rel_end])
        return self.join_tokens(rel_start, rel_end)

    def _format_brackets(self, text: str, index: int, color: str) -> str:
        """Format text with brackets"""
        if self.discarded:
            return f"<div class='discarded-text'> {text} </div>"
        else:
            return f"<span class='bracket-font'> :{color}-background[:{color}[{index} \[]]</span>" + text + f"<span class='bracket-font'>:{color}-background[:{color}[\]]]</span>"

    def format_section_text(self, cursor_start: int, cursor_end: int, cursor_color: str, is_selected: bool, index: int = None, color: str = "red") -> str:
        # Check if cursors interact with section
        start_in_bounds = self.spans[0] <= cursor_start <= self.spans[1]
        end_in_bounds = self.spans[0] <= cursor_end <= self.spans[1]

        if not (start_in_bounds or end_in_bounds):
            # No interaction - return plain formatted text
            return self._format_brackets(self.text, index, color) if not is_selected else self.text

        # Build text in parts
        text_parts = []

        # Add text before start cursor
        if start_in_bounds:
            text_parts.append(self._slice_text(self.spans[0], cursor_start))

            text_parts.append(f"<span class='bracket-font'>:{cursor_color}-background[:{cursor_color}[\[]]</span>")
            marked_txt = self._slice_text(cursor_start, cursor_end + 1 if end_in_bounds else self.spans[1])
            # mark text with background color
            text_parts.append("\n\n".join([f":{cursor_color}-background[{x}]" for x in marked_txt.split('\n\n')]))
        else:
            # text_parts.append(self._slice_text(self.spans[0], cursor_end))
            marked_txt = self._slice_text(self.spans[0], cursor_end)
            text_parts.append("\n\n".join([f":{cursor_color}-background[{x}]" for x in marked_txt.split('\n\n')]))

        # Add end marker if applicable
        if end_in_bounds:
            text_parts.append(f"<span class='bracket-font'>:{cursor_color}-background[:{cursor_color}[\]]]</span>")
            text_parts.append(self._slice_text(cursor_end, self.spans[1]))

        result = "".join(text_parts)
        return result if is_selected else self._format_brackets(result, index, color)

    def format_section_split_text(self, cursor_pos: int):
        span_before = self._slice_text(self.spans[0], cursor_pos)
        span_after = self._slice_text(cursor_pos, self.spans[1])
        return span_before + " :red-background[:red[|B|]] " + span_after

    def __repr__(self):
        return f"Section: {self.title} - {self.spans}"

    def __str__(self):
        return f"Section: {self.title} - {self.spans}"


class PDFHandler:

    def __init__(self, sections: List[Section]):
        self.sections = sections
        self.discarded_ids = []

    @classmethod
    def from_markdown(cls, markdown: str):
        """"""
        # build sections
        pdf_tokens: List[str] = []
        pdf_sections: List[Section] = []

        section_indx = 0

        for markdwn_section in markdown.split('## '):
            if markdwn_section and markdwn_section != "\n":
                section = Section(
                    id_=section_indx,
                    text=markdwn_section,
                    title=markdwn_section.split('\n')[0]
                )

                # get section tokens
                start = len(pdf_tokens)
                pdf_tokens.extend(section.tokens)
                end = len(pdf_tokens) - 1

                # update spans
                section.spans = (start, end)
                pdf_sections.append(section)

                section_indx += 1

        return PDFHandler(pdf_sections)

    @classmethod
    def from_unstructured_chunks(cls, chunks: List):
        """Method to create a PDFHandler object from unstructured chunks"""

        # build sections
        pdf_tokens: List[str] = []
        pdf_sections: List[Section] = []

        for i, comp_ele in enumerate(chunks):
            # if orig_elements in binary transform to unstructured Element objects
            if isinstance(comp_ele.metadata.orig_elements, bytes):
                comp_ele.metadata.orig_elements = cls._extract_orig_elements(comp_ele.metadata.orig_elements)

            section = Section(
                id_=i,
                text=comp_ele.text,
                title=comp_ele.metadata.orig_elements[0].text
            )
            # Get tokens using Section's method
            start = len(pdf_tokens)
            pdf_tokens.extend(section.tokens)
            end = len(pdf_tokens) - 1

            # Update spans and add to sections
            section.spans = (start, end)
            pdf_sections.append(section)

        return PDFHandler(pdf_sections)

    def to_json(self) -> str:
        return json.dumps({"sections": [section.__dict__ for section in self.sections if not section.discarded]})

    def get_pdf_tokens(self):
        """Get all tokens from PDF"""
        return [token for section in self.sections for token in section.tokens]

    def update_section_spans(self, section_index: int, start: int, end: int):
        pass

    def discard_section(self, section_index: int):
        """Change state of section to discarded"""
        self.sections[section_index].discarded = True

    def get_discarded_sections(self) -> List[int]:
        """Get all discarded sections"""
        return [section.id_ for section in self.sections if section.discarded]

    def join_sections(self, section_one_indx: int, section_two_inxd: int, new_title: str):
        """Join two sections together"""
        # TODO: join with leading section does not work??
        section_to_be_joined = self.sections[min(section_one_indx, section_two_inxd)]

        section_after = self.sections.pop(max(section_one_indx, section_two_inxd))
        new_section = Section(
            id_=section_one_indx,
            text=section_to_be_joined.text + ' ' + section_after.text,
            title=new_title,
            spans=(section_to_be_joined.spans[0], section_after.spans[1])
        )

        self.sections[min(section_one_indx, section_two_inxd)] = new_section

        # update section ids
        self._update_section_ids()

    def commit_section_slice(self, slicer):
        """Method to create new sections based on slicing"""
        # first initialize new section with slider bounds
        selected_slice = Section(
            id_=slicer.current_section_indx,
            text=slicer.get_slider_slice(),
            title=slicer.current_section.title,
            spans=(slicer.slider_start, slicer.slider_end)
        )
        # second check if leading and trailing sections are inbounds
        if slicer.leading_section_inbounds:
            leading_slice = Section(
                id_=slicer.current_section_indx - 1,
                text=slicer.get_leading_slice(),
                title=slicer.leading_section_title,
                spans=(slicer.current_section.spans[0], slicer.slider_start - 1)
            )
        if slicer.traling_section_inbounds:
            trailing_slice = Section(
                id_=slicer.current_section_indx + 1,
                text=slicer.get_trailing_slice(),
                title=slicer.trailing_section_title,
                spans=(slicer.slider_end + 1, slicer.current_section.spans[1])
            )
        # third check if leading and trailing sections overflow
        if slicer.leading_section_overflow:
            leading_section = self.sections[slicer.current_section_indx - 1]
            leading_slice = Section(
                id_=slicer.current_section_indx - 1,
                text=leading_section._slice_text(leading_section.spans[0], slicer.slider_start - 1),
                spans=(leading_section.spans[0], slicer.slider_start - 1)
            )
            # replace leading section with new slice
            self.sections[slicer.current_section_indx - 1] = leading_slice
        if slicer.traling_section_overflow:

            trailing_section = self.sections[slicer.current_section_indx + 1]
            trailing_slice = Section(
                id_=slicer.current_section_indx + 1,
                text=trailing_section._slice_text(slicer.slider_end + 1, trailing_section.spans[1]),
                spans=(slicer.slider_end + 1, trailing_section.spans[1])
            )
            # replace trailing section with new slice
            self.sections[slicer.current_section_indx + 1] = trailing_slice
        # update sections
        self.sections[slicer.current_section_indx] = selected_slice
        if slicer.leading_section_inbounds:
            # check if adjacent or new section
            if slicer.leading_section_inbounds_method == 0:
                # append to leading section
                self.sections[slicer.current_section_indx - 1].text += " " + leading_slice.text
                # update spans
                self.sections[slicer.current_section_indx
                              - 1].spans = (self.sections[slicer.current_section_indx - 1].spans[0], slicer.slider_start - 1)
            elif slicer.leading_section_inbounds_method == 1 or slicer.leading_section_inbounds_method == 2:
                # insert leading slice
                self.sections.insert(slicer.current_section_indx, leading_slice)
                # set section to discard
                if slicer.leading_section_inbounds_method == 2:

                    self.sections[slicer.current_section_indx
                                  - 1 if slicer.current_section_indx > 0 else 0].discarded = True

        if slicer.traling_section_inbounds:
            # check if adjacent or new section
            if slicer.traling_section_inbounds_method == 0:
                # append to trailing section
                self.sections[slicer.current_section_indx + 1].text = trailing_slice.text + \
                    " " + self.sections[slicer.current_section_indx + 1].text
                # update spans
                self.sections[slicer.current_section_indx
                              + 1].spans = (slicer.slider_end + 1, self.sections[slicer.current_section_indx + 1].spans[1])
            elif slicer.traling_section_inbounds_method == 1 or slicer.traling_section_inbounds_method == 2:
                # insert trailing slice
                self.sections.insert(
                    slicer.current_section_indx + 2 if slicer.leading_section_inbounds else slicer.current_section_indx + 1, trailing_slice)
                # set section to discard
                if slicer.traling_section_inbounds_method == 2:
                    self.sections[slicer.current_section_indx + 1 if slicer.current_section_indx
                                  < len(self.sections) - 1 else slicer.current_section_indx].discarded = True

        # update section ids
        self._update_section_ids()

    def commit_section_slicing(self,
                               section_indx: int,
                               cursor_start: int,
                               cursor_end: int,
                               new_section_title: str,
                               isolated_part_before: bool,
                               isolated_part_after: bool,
                               part_before_title: Optional[str] = None,
                               part_after_title: Optional[str] = None,
                               ):
        # set current section
        section = self.sections[section_indx]

        # create sliced section
        sliced_section = Section(
            id_=section_indx,
            text=section._slice_text(cursor_start, cursor_end),
            title=new_section_title,
            spans=(cursor_start, cursor_end)
        )

        self.sections[section_indx] = sliced_section

        # behavior for new section and discard same same? -> first step is to create new section
        if isolated_part_before:
            # create new section
            section_before = Section(
                id_=section_indx,
                text=section._slice_text(section.spans[0], cursor_start - 1),
                title=part_before_title,
                spans=(section.spans[0], cursor_start - 1)
            )

            self.sections.insert(section_indx, section_before)

        if isolated_part_after:
            # create new section
            section_after = Section(
                id_=section_indx + 1,
                text=section._slice_text(cursor_end + 1, section.spans[1]),
                title=part_after_title,
                spans=(cursor_end + 1, section.spans[1])
            )

            self.sections.insert(section_indx + 2 if isolated_part_before else section_indx + 1, section_after)

        # update section spans
        section.spans = (cursor_start + 1, cursor_end - 1)

        self._update_section_ids()

    def _update_section_ids(self):
        for i, sect in enumerate(self.sections):
            sect.id_ = i

    def split_sections(self, section_indx: int, section_break_indx: int, first_title: str, second_title: str):
        section = self.sections[section_indx]

        first_section = Section(
            id_=section_indx,
            text=section._slice_text(section.spans[0], section_break_indx),
            title=first_title,
            spans=(section.spans[0], section_break_indx)
        )
        second_section = Section(
            id_=section_indx + 1,
            text=section._slice_text(section_break_indx, section.spans[1]),
            title=second_title,
            spans=(section_break_indx, section.spans[1])
        )

        self.sections[section_indx] = first_section

        self.sections.insert(section_indx + 1, second_section)

        # update section ids
        self._update_section_ids()

    def get_sections_text(self, editable_section_index: int):
        pass

    def save_state(self, file_path: str):
        """Save sections state to file"""
        state = {
            "sections": [section.__dict__ for section in self.sections]
        }

        with open(file_path, "w") as fh:
            json.dump(state, fh, indent=3)

    def load_state(self, file_path: str):
        """Load sections state from file"""
        with open(file_path, "r") as fh:
            state = json.load(fh)

        sections: List[Section] = []
        for section in state["sections"]:
            section.pop("tokens")
            sections.append(Section(**section))
        self.sections = [Section(**section) for section in state["sections"]]

    @staticmethod
    def _extract_orig_elements(orig_elements):
        """Helper method to decode unstructured.element objects"""
        decoded_orig_elements = base64.b64decode(orig_elements)
        decompressed_orig_elements = zlib.decompress(decoded_orig_elements)
        return decompressed_orig_elements.decode('utf-8')


class SectionSlicer:
    """Handles section operations when slicing sections in a PDF."""

    # Define section options
    SECTION_OPTIONS = {
        0: ":material/merge_type: Append to adjacent Section",
        1: ":material/add: New Section",
        2: ":material/delete: Discard"
    }

    def __init__(
        self,
        section_index: int,
        pdf_handler: PDFHandler,
        slider_start: int,
        slider_end: int
    ):
        self.current_section_indx = section_index
        self.pdf_handler = pdf_handler
        self.current_section = pdf_handler.sections[section_index]
        # position of slider
        self.slider_start = slider_start
        self.slider_end = slider_end
        # new titles for adjacent sections (inbounds)
        self.leading_section_title = None
        self.trailing_section_title = None

        # set possible cases
        self.leading_section_inbounds = slider_start > self.current_section.spans[0]
        self.traling_section_inbounds = slider_end < self.current_section.spans[1]
        self.leading_section_overflow = slider_start < self.current_section.spans[0] and section_index > 0
        self.traling_section_overflow = slider_end > self.current_section.spans[1] and section_index < len(
            pdf_handler.sections) - 1

        # SECTION_OPTIONS.key
        self.leading_section_inbounds_method = 2 if self.leading_section_inbounds else None
        self.traling_section_inbounds_method = 2 if self.traling_section_inbounds else None

    def get_options(self, case: Literal["leading", "trailing"]) -> dict:
        if case == "leading":
            if self.current_section_indx == 0:
                return {k: v for k, v in self.SECTION_OPTIONS.items() if k != 0}
            else:
                return self.SECTION_OPTIONS
        elif case == "trailing":
            if self.current_section_indx == len(self.pdf_handler.sections) - 1:
                return {k: v for k, v in self.SECTION_OPTIONS.items() if k != 0}
            else:
                return self.SECTION_OPTIONS
        else:
            raise TypeError("\'case\' paremter must be either \'leading\' or \'trailing\'.")

    def get_leading_slice(self) -> str:
        """Get text of leading in bounds slice"""
        # TODO: overflow,  not inbounds
        return self.current_section._slice_text(self.current_section.spans[0], self.slider_start - 1)

    def get_trailing_slice(self) -> str:
        """Get text of trailing in bounds slice"""
        # TODO: overflow,  not inbounds
        return self.current_section._slice_text(self.slider_end, self.current_section.spans[1] + 1)

    def get_slider_slice(self) -> str:
        # check if inbounds or overflow into next section
        if not self.leading_section_overflow and not self.traling_section_overflow:
            return self.current_section._slice_text(self.slider_start, self.slider_end)
        elif self.leading_section_overflow and not self.traling_section_overflow:
            # get part of leading section
            leading_section = self.pdf_handler.sections[self.current_section_indx - 1]
            # return leading_section._slice_text(leading_section.spans[0], self.slider_end) + self.get_trailing_slice()
            return leading_section._slice_text(self.slider_start, leading_section.spans[1]) + " " + self.current_section._slice_text(self.current_section.spans[0], self.slider_end)
        elif not self.leading_section_overflow and self.traling_section_overflow:
            trailing_section = self.pdf_handler.sections[self.current_section_indx + 1]
            return self.current_section._slice_text(self.slider_start, self.current_section.spans[1]) + " " + trailing_section._slice_text(trailing_section.spans[0], self.slider_end)
        else:
            leading_section = self.pdf_handler.sections[self.current_section_indx - 1]
            trailing_section = self.pdf_handler.sections[self.current_section_indx + 1]
            return leading_section._slice_text(self.slider_start, leading_section.spans[1]) + " " + self.current_section._slice_text(self.current_section.spans[0], self.current_section.spans[1]) + " " + trailing_section._slice_text(trailing_section.spans[0], self.slider_end)
