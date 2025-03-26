from typing import Tuple, List
import torch

from docling_core.types.doc.document import DocTagsDocument, DoclingDocument

from PIL import Image
from transformers import AutoProcessor, AutoModelForVision2Seq
# from transformers.image_utils import load_image


VLLM_MODEL = "ds4sd/SmolDocling-256M-preview"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


PROMPT_MESSAGES = [
    {
        "role": "user",
        "content": [
            {"type": "image"},
            {"type": "text", "text": "Convert this page to docling."}
        ]
    }
]


def pdf_to_docling(pdf_images: List[Image.Image], pdf_title: str, processor: AutoProcessor, model: AutoModelForVision2Seq) -> DoclingDocument:

    # init docling document
    doc = DoclingDocument(name=pdf_title)
    doctags_list = []

    # Process each page with VLLM
    for page_number, pil_image in enumerate(pdf_images, start=1):
        print(f"Processing page {page_number} ...")
        doctags = pdf_image_to_docling(pil_image, pdf_title, page_number, processor, model)
        doctags_list.append(doctags)

    # build doctag document
    doctags_doc = DocTagsDocument.from_doctags_and_image_pairs(doctags_list, pdf_images)
    doc.load_from_doctags(doctags_doc)

    return doc


def pdf_image_to_docling(image, doc_title: str, page_number: int, processor: AutoProcessor, model: AutoModelForVision2Seq) -> DoclingDocument:
    # Prepare Inputs
    prompt = processor.apply_chat_template(PROMPT_MESSAGES, add_generation_prompt=True)
    inputs = processor(text=prompt, images=[image], return_tensors="pt")
    inputs = inputs.to(DEVICE)

    # Generate Outputs
    generated_ids = model.generate(**inputs, max_new_tokens=8192)
    prompt_length = inputs.input_ids.shape[1]
    trimmed_generated_ids = generated_ids[:, prompt_length:]
    doctags = processor.batch_decode(
        trimmed_generated_ids,
        skip_special_tokens=False,
    )[0].lstrip()

    return doctags


def init_processor_and_model() -> Tuple[AutoProcessor, AutoModelForVision2Seq]:
    # method to init AutoProcessor and VLLM
    processor = AutoProcessor.from_pretrained(VLLM_MODEL)

    model = AutoModelForVision2Seq.from_pretrained(
        VLLM_MODEL,
        torch_dtype=torch.bfloat16,
        _attn_implementation="flash_attention_2" if DEVICE == "cuda" else "eager"
    ).to(DEVICE)

    return processor, model
