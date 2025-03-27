import os
import json
from io import BytesIO
from pdf2image import convert_from_path
import streamlit as st
import streamlit.components.v1 as components
from docling_core.types.doc.document import DoclingDocument
from nice_processing import init_processor_and_model, pdf_to_docling
from pdfhandler import PDFHandler, Section, SectionSlicer

STAGE_PATH = "/workspaces/NicerSlicer/stage"
DOCLING_JSON = "docling.json"
SECTION_JSON = "sections.json"

# ---- STREAMLIT STYLE ----
BRACKET_COLORS = ["red", "blue", "orange", "green"]
st.set_page_config(layout="wide")
st.html("<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&icon_names=text_select_move_forward_character' />")
st.markdown(
    """<style>

div[data-testid="stDialog"] div[role="dialog"]:has(.big-dialog) {
    width: 80vw;
}

.bracket-font {
    font-size: 25px !important;
    vertical-align: -7%;
}

.discarded-text {
    color: gray;
}

.selected-container {
    background-color: blue;
}

.material-symbols-outlined {
  font-variation-settings:
  'FILL' 0,
  'wght' 400,
  'GRAD' 0,
  'opsz' 24
}
</style>
""",
    unsafe_allow_html=True,
)


# ---- Helper Methods ----

def format_section_option(section: Section) -> str:
    return f"{section.id_} - {section.title}"


def id_from_section_option(section_option: str) -> int:
    return int(section_option.split("-")[0].strip())


def discard_section(pdf_handler: PDFHandler):
    # set section to discard status
    pdf_handler.sections[st.session_state.selected_section_index].discarded = True
    # store state
    pdf_handler.save_state(os.path.join(STAGE_PATH, st.session_state.selected_document, SECTION_JSON))
    # update session state
    st.session_state.discarded_sections = pdf_handler.get_discarded_sections()

# ---- Cached Methods ----


@st.cache_data
def load_pdf_markdown(doc_folder: str) -> str:
    # init DoclingDocument from json
    docling = DoclingDocument.load_from_json(os.path.join(STAGE_PATH, doc_folder, DOCLING_JSON))
    return docling.export_to_markdown(image_placeholder="")


# ---- STREAMLIT SESSION STATE ----
if "selected_document" not in st.session_state:
    st.session_state.selected_document = None
if "document_bounds" not in st.session_state:
    st.session_state.document_bounds = None
if "selected_section_index" not in st.session_state:
    st.session_state.selected_section_index = None
if "discarded_sections" not in st.session_state:
    st.session_state.discarded_sections = []
if "selected_color" not in st.session_state:
    st.session_state.selected_color = None

# ---- STREAMLIT Dialogs ----


@st.dialog("Join Sections")
def join_sections(section_index, pdf_handler):

    # set joinable sections
    if section_index == 0:
        leading_section = None
        trailing_section = pdf_handler.sections[section_index + 1]

        join_section_options = [f"Section {trailing_section.id_}"]
        join_section_captions = [trailing_section.title]

    elif section_index == len(pdf_handler.sections) - 1:
        leading_section = pdf_handler.sections[section_index + - 1]
        trailing_section = None

        join_section_options = [f"Section {leading_section.id_}"]
        join_section_captions = [leading_section.title]

    else:
        leading_section = pdf_handler.sections[section_index - 1]
        trailing_section = pdf_handler.sections[section_index + 1]

        join_section_options = [f"Section {s.id_}" for s in [leading_section, trailing_section]]
        join_section_captions = [leading_section.title, trailing_section.title]

    # streamlit dialog elements
    join_with = st.radio(
        "Do you want to join the section with the predecessor or successor?",
        join_section_options,
        captions=join_section_captions
    )

    # join_with_select = st.segmented_control(
    #     "Do you want to join the section with the predecessor or successor?",
    #     options={s.id_: f"Section {s.id_}" for s in [section_before, section_after]},
    #     selection_mode="single",
    #     default=section_before.id_
    # )
    title_options = [pdf_handler.sections[i].title for i in sorted(
        [section_index, int(join_with.replace("Section ", ""))])]

    title_options.append("New Title ...")

    section_title = st.selectbox(
        "Enter the Title for the Section",
        title_options,
    )

    if section_title == title_options[-1]:
        new_title = st.text_input(label="New Title")

    if st.button("Commit", type="primary"):
        # check new title not empty

        # commit join and persist changes
        if section_title == title_options[-1]:
            pdf_handler.join_sections(section_index, int(join_with.replace("Section ", "")), new_title)
        else:
            pdf_handler.join_sections(section_index, int(join_with.replace("Section ", "")), section_title)

        # update discard session state
        st.session_state.discarded_sections = pdf_handler.get_discarded_sections()

        pdf_handler.save_state(os.path.join(STAGE_PATH, st.session_state.selected_document, SECTION_JSON))

        st.rerun()


@st.dialog("Split Section")
def split_sections(section_index: int, pdf_handler: PDFHandler, slider_start: int, slider_end: int):

    section = pdf_handler.sections[section_index]

    split_col1, split_col2 = st.columns(2)
    with split_col1:
        title1 = st.text_input("Title of first Part", value=section.title)
    with split_col2:
        title2 = st.text_input("Title of second Part")

    # check if slider was moved to separate section
    # Check if cursors interact with section
    start_in_bounds = section.spans[0] < slider_start < section.spans[1]
    end_in_bounds = section.spans[0] < slider_end < section.spans[1]

    # no slider ranges in section
    if not (start_in_bounds or end_in_bounds):
        # if newline in paragraph set cursor
        if section.NEWLINE_TOKEN in section.tokens:
            cursor = section.tokens.index(section.NEWLINE_TOKEN) + section.spans[0]
        else:
            cursor = section.spans[0]
    elif start_in_bounds:
        cursor = slider_start
    elif end_in_bounds:
        cursor = slider_end

    # create streamlit slider for section split
    section_separator = st.slider("Set Separator", min_value=section.spans[0], max_value=section.spans[1], value=cursor)
    st.divider()
    st.markdown(section.format_section_split_text(section_separator))

    st.divider()

    if st.button("Commit", type="primary"):
        pdf_handler.split_sections(section_index, section_separator, title1, title2)
        # update discard session state
        st.session_state.discarded_sections = pdf_handler.get_discarded_sections()
        pdf_handler.save_state(os.path.join(STAGE_PATH, st.session_state.selected_document, SECTION_JSON))

        st.rerun()

    st.html("<span class='big-dialog'></span>")


@st.dialog("Commit Section")
def commmit_section(section_index: int, pdf_handler: PDFHandler, slider_start: int, slider_end: int):
    # TODO: adjascent sections and discard section
    slicer = SectionSlicer(
        section_index=section_index,
        pdf_handler=pdf_handler,
        slider_start=slider_start,
        slider_end=slider_end
    )

    # WARNINGS
    if slicer.leading_section_inbounds or slicer.traling_section_inbounds:
        st.warning(
            'You sliced one or more isolated parts of the original section. Define below how to proceed with these parts.', icon="⚠️")
    if slicer.leading_section_overflow or slicer.traling_section_overflow:
        st.warning(
            'Be aware that your section exceeds the bounds of other Sections. These Slices will be integrated into your current Section.')

    if slicer.leading_section_inbounds and slicer.traling_section_inbounds:
        leading_width, trailing_width = 0.5, 0.5
    elif slicer.leading_section_inbounds:
        leading_width, trailing_width = 0.95, 0.05
    elif slicer.traling_section_inbounds:
        leading_width, trailing_width = 0.05, 0.95
    else:
        leading_width, trailing_width = 0.5, 0.5
    leading_section_col, trailing_section_col = st.columns([leading_width, trailing_width])

    # init streamlit columns based on slicer.leading_section_inbounds and slicer.traling_section_inbounds

    # Case of in bounds leading section
    if slicer.leading_section_inbounds:
        leading_options = slicer.get_options("leading")
        with leading_section_col:
            st.markdown("**Leading Isolated Part**")
            st.container(border=True).write(slicer.get_leading_slice())
            slicer.leading_section_inbounds_method = st.segmented_control(
                "How do you want to proceed?",
                options=leading_options.keys(),
                format_func=lambda option: leading_options[option],
                selection_mode="single",
                default=2,
                key="leading_section_selection"
            )
            if slicer.leading_section_inbounds_method == 1:
                slicer.leading_section_title = st.text_input(
                    "Leading Section Title", placeholder="New Section Title", key="leading_section_title_input")

    # Case of in bounds trailing section
    if slicer.traling_section_inbounds:
        trailing_options = slicer.get_options("trailing")
        with trailing_section_col:
            st.markdown("**Trailing Isolated Part**")
            st.container(border=True).write(slicer.get_trailing_slice())
            slicer.trailing_section_inbounds_method = st.segmented_control(
                "How do you want to proceed?",
                options=trailing_options.keys(),
                format_func=lambda option: trailing_options[option],
                selection_mode="single",
                default=2,
                key="trailing_section_selection"
            )
            if slicer.trailing_section_inbounds_method == 1:
                slicer.trailing_section_title = st.text_input(
                    "Trailing Section Title", placeholder="New Section Title", key="trailing_section_title_input")

    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col2:
        if st.button(":material/save: Commit Slicing", type="primary"):
            pdf_handler.commit_section_slice(slicer)
            # get discard sections
            discarded_sections = pdf_handler.get_discarded_sections()

            if discarded_sections:

                st.session_state.discarded_sections = discarded_sections

            pdf_handler.save_state(os.path.join(STAGE_PATH, st.session_state.selected_document, SECTION_JSON))

            st.rerun()

    st.html("<span class='big-dialog'></span>")

# ---- STREAMLIT LAYOUT ----


st.title("Nicer Slicer :scissors:")

alert_container = st.container()

# check stage for existing file
upload_tab, slice_tab = st.tabs(["Upload Document", "Slice Document"])


# ---- SIDEBAR----
with st.sidebar:
    st.header("PDF Settings")

    st.session_state.selected_document = st.selectbox(
        "Select your Document",
        [doc_folder for doc_folder in os.listdir(STAGE_PATH)]
    )
    with st.status("Load Document..."):
        dolcing_markdown = load_pdf_markdown(st.session_state.selected_document)
        pdf_handler = PDFHandler.from_markdown(dolcing_markdown)

        if os.path.exists(os.path.join(STAGE_PATH, st.session_state.selected_document, SECTION_JSON)):
            pdf_handler.load_state(os.path.join(STAGE_PATH, st.session_state.selected_document, SECTION_JSON))

    st.divider()

    st.header("Section Editor")

    # section selector
    st.session_state.selected_section_index = id_from_section_option(st.selectbox(
        "Edit Section",
        options=[format_section_option(s) for s in pdf_handler.sections],
        key="section-select"
    ))
    selected_section = pdf_handler.sections[st.session_state.selected_section_index]

    # build slider for section boundaries
    lower_boundaries = max(0, selected_section.spans[0] - 80)
    range_options = [i for i in range(lower_boundaries, selected_section.spans[1] + 80)]
    slider_start, slider_end = st.select_slider(
        "Section Boundaries",
        options=range_options,
        value=(selected_section.spans[0], selected_section.spans[1]),
        key="chunk-boundaries"
    )

    side_col1, side_col2, side_col3 = st.columns([0.1, 1, 0.1], vertical_alignment="bottom")
    with side_col2:
        st.markdown(
            """
            <style>
            div.stButton > button {
                width: 100%;
            }
            div.stDownloadButton > button {
                width: 100%
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        if st.button("Commit Section", key="commit-section-boundaries", icon=":material/playlist_add:"):
            commmit_section(st.session_state.selected_section_index, pdf_handler, slider_start, slider_end)
    st.divider()
    st.header("Section Operations")
    side_col_4, side_col_5, side_col_6 = st.columns(3)
    with side_col_4:
        st.button(
            "Discard",
            type="tertiary",
            key="discard_section",
            icon=":material/delete:",
            help="Delete the selected section",
            on_click=discard_section,
            args=[pdf_handler]
        )
    with side_col_5:
        if st.button("Join", type="tertiary", key="join-sections",
                     icon=":material/merge_type:", help="Join this section with another one"):
            join_sections(st.session_state.selected_section_index, pdf_handler, )
    with side_col_6:
        if st.button("Split", type="tertiary", key="split-sections",
                     icon=":material/call_split:", help="Split this section into two"):
            split_sections(st.session_state.selected_section_index, pdf_handler, slider_start, slider_end)

    st.divider()
    st.download_button(
        "Download Sections",
        key="download-sections",
        icon=":material/download:",
        data=pdf_handler.to_json(),
        mime="application/json",
        file_name=st.session_state.selected_document
    )


# ---- UPLOAD TAB ----

with upload_tab:

    upload_col1, upload_col2, upload_col3 = st.columns([1, 2, 1])

    with upload_col2:

        pdf_doc_title = st.text_input("Document Title", placeholder="Your PDF Title")
        uploaded_file = st.file_uploader("Choose your pdf", accept_multiple_files=False)

        if st.button("Process", type="primary", disabled=False if uploaded_file else True, icon="💫"):
            with st.status("Processing uploaded PDF...", expanded=True) as status:
                st.write("Reading PDF...")
                # creat sub folder and file path
                dir_path = os.path.join(STAGE_PATH, pdf_doc_title)
                if not os.path.exists(dir_path):
                    os.mkdir(dir_path)
                file_path = os.path.join(dir_path, f"{pdf_doc_title}.pdf")
                # store pdf file
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getvalue())

                # convert pdf to images
                st.write("Convert PDF to Images...")
                images = convert_from_path(file_path, dpi=300)

                st.write("Initialize VLLM Model")
                processor, vllm = init_processor_and_model()

                st.write("Processing PDF to Docling...")
                docling_doc = pdf_to_docling(
                    pdf_images=images,
                    pdf_title=pdf_doc_title,
                    processor=processor,
                    model=vllm
                )

                st.write("Persisting DoclingDocument")
                docling_path = os.path.join(dir_path, "docling.json")

                with open(docling_path, "w") as fh:
                    json.dump(docling_doc.export_to_dict(), fh)


# ---- Slice TAB ----
with slice_tab:
    if st.session_state.selected_document:
        for section_index, section in enumerate(pdf_handler.sections):
            if section.id_ in st.session_state.discarded_sections:

                section.discarded = True
            # set color and state bool
            section_color = BRACKET_COLORS[section_index % len(BRACKET_COLORS)]
            is_selected = True if section_index == st.session_state.selected_section_index else False
            if is_selected:
                st.session_state.selected_color = section_color
            # get text from section object
            txt = section.format_section_text(
                slider_start, slider_end, cursor_color=st.session_state.selected_color, is_selected=is_selected, index=section_index, color=section_color
            )
            st.markdown(txt, unsafe_allow_html=True)

        # st.markdown(docling_doc.export_to_markdown())
