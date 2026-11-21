if [ "$(uname -s)" = "Darwin" ]; then
    open "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/tree/master/Models"
    open "https://www.modelscope.cn/models/aihobbyist/RVC_Model_Collection/summary"
    open "https://pitch-family-06a.notion.site/AI-RVC-edee304e62974c52b4ffe676afbb264a"
    open "https://huggingface.co/chaye741/RVC-Voice-Models"
fi
if [ "$(uname -s)" = "Linux" ]; then
    xdg-open "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/tree/master/Models"
    xdg-open "https://www.modelscope.cn/models/aihobbyist/RVC_Model_Collection/summary"
    xdg-open "https://pitch-family-06a.notion.site/AI-RVC-edee304e62974c52b4ffe676afbb264a"
    xdg-open "https://huggingface.co/chaye741/RVC-Voice-Models"
fi
if [ "$(uname -s)" = "MINGW32_NT" ]; then
    start "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/tree/master/Models"
    start "https://www.modelscope.cn/models/aihobbyist/RVC_Model_Collection/summary"
    start "https://pitch-family-06a.notion.site/AI-RVC-edee304e62974c52b4ffe676afbb264a"
    start "https://huggingface.co/chaye741/RVC-Voice-Models"
fi
