from ..data_types.data_types import BeatriceV2SampleInfo, SampleInfoMember

SAMPLE_BEATRICE_V2_ALPHA: list[SampleInfoMember] = [
    BeatriceV2SampleInfo(
        id="beatriceV2Alpha",
        voice_changer_type="Beatrice_v2",
        lang="ja-JP",
        tag=[],
        name="JVS(V2Alpha)",
        terms_of_use_url="https://huggingface.co/wok000/vcclient_model/blob/main/beatrice_v2_alpha/readme.md",
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/beatrice_v2_alpha/BeatriceAPIJVSCorpus.png",
        credit="Project Beatrice",
        description="",
        zip_url="https://huggingface.co/wok000/vcclient_model/resolve/main/beatrice_v2_alpha/beatrice_v2_jvs_corpus_alpha.zip",
    ),
    BeatriceV2SampleInfo(
        id="beatriceV2Beta",
        voice_changer_type="Beatrice_v2",
        lang="ja-JP",
        tag=[],
        name="JVSV2Beta",
        terms_of_use_url="https://huggingface.co/wok000/vcclient_model/blob/main/beatrice_v2_beta/readme.md",
        icon_url="https://huggingface.co/wok000/vcclient_model/resolve/main/beatrice_v2_beta/BeatriceAPIJVSCorpus_beta.png",
        credit="Project Beatrice",
        description="",
        zip_url="https://huggingface.co/wok000/vcclient_model/resolve/main/beatrice_v2_beta/beatrice_v2_jvs_corpus_beta.zip",
    ),
]
