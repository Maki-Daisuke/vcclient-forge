!/bin/bash

echo "========================================="
echo "VCClient 文件手动下载和安装脚本"
echo "========================================="

# 设置目录
DOWNLOAD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ScriptTemp"
VCCLIENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd $(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# 创建下载目录
mkdir -p "$DOWNLOAD_DIR"
echo "✓ 下载目录已创建: $DOWNLOAD_DIR"

echo ""
echo "开始下载文件..."
echo ""

# 1. 下载 rmvpe
echo "正在下载: rmvpe_20231006.onnx"
curl -L -k --progress-bar -o "$DOWNLOAD_DIR/rmvpe_20231006.onnx" "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/resolve/master/Runtime/rmvpe/rmvpe_20231006.onnx?view=false"
if [ $? -eq 0 ]; then echo "✓ rmvpe_20231006.onnx 下载完成"; else echo "✗ rmvpe_20231006.onnx 下载失败"; fi
echo ""

# 2. 下载 rinna_hubert
echo "正在下载: rinna_hubert_base-f.onnx"
curl -L -k --progress-bar -o "$DOWNLOAD_DIR/rinna_hubert_base-f.onnx" "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/resolve/master/Runtime/rinna_hubert/rinna_hubert_base-f.onnx?view=false"
if [ $? -eq 0 ]; then echo "✓ rinna_hubert_base-f.onnx 下载完成"; else echo "✗ rinna_hubert_base-f.onnx 下载失败"; fi
echo ""

# 3. 下载 fcpe
echo "正在下载: fcpe.onnx"
curl -L -k --progress-bar -o "$DOWNLOAD_DIR/fcpe.onnx" "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/resolve/master/Runtime/fcpe/fcpe.onnx?view=false"
if [ $? -eq 0 ]; then echo "✓ fcpe.onnx 下载完成"; else echo "✗ fcpe.onnx 下载失败"; fi
echo ""

# 4. 下载 contentvec
echo "正在下载: contentvec-f.onnx"
curl -L -k --progress-bar -o "$DOWNLOAD_DIR/contentvec-f.onnx" "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/resolve/master/Runtime/contentvec/contentvec-f.onnx?view=false"
if [ $? -eq 0 ]; then echo "✓ contentvec-f.onnx 下载完成"; else echo "✗ contentvec-f.onnx 下载失败"; fi
echo ""

# 5. 下载 tsukuyomi 模型
echo "正在下载: tsukuyomi_v2_40k_e100_float.onnx"
curl -L -k --progress-bar -o "$DOWNLOAD_DIR/tsukuyomi_v2_40k_e100_float.onnx" "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/resolve/master/Runtime/UploadDir/tsukuyomi_v2_40k_e100_float.onnx?view=false"
if [ $? -eq 0 ]; then echo "✓ tsukuyomi_v2_40k_e100_float.onnx 下载完成"; else echo "✗ tsukuyomi_v2_40k_e100_float.onnx 下载失败"; fi
echo ""

echo "正在下载: tsukuyomi_chan.png"
curl -L -k --progress-bar -o "$DOWNLOAD_DIR/tsukuyomi_chan.png" "https://www.modelscope.cn/models/HelloWorldCoder/VCC-Forged-RVC-Models/resolve/master/Runtime/UploadDir/tsukuyomi_chan.png?view=false"
if [ $? -eq 0 ]; then echo "✓ tsukuyomi_chan.png 下载完成"; else echo "✗ tsukuyomi_chan.png 下载失败"; fi
echo ""

echo "========================================="
echo "下载完成！开始复制文件..."
echo "========================================="
echo ""

# 检查 VCClient 目录是否存在
if [ ! -d "$VCCLIENT_DIR" ]; then
    echo "✗ 错误: 找不到 VCClient 目录: $VCCLIENT_DIR"
    exit 1
fi

# 创建目标目录结构
mkdir -p "$VCCLIENT_DIR/modules/rmvpe"
mkdir -p "$VCCLIENT_DIR/modules/rinna_hubert"
mkdir -p "$VCCLIENT_DIR/modules/fcpe"
mkdir -p "$VCCLIENT_DIR/modules/contentvec"
mkdir -p "$VCCLIENT_DIR/upload_dir"

echo "✓ 目录结构已创建"
echo ""

# 复制文件到对应位置
echo "正在复制文件..."

# 1. rmvpe
if [ -f "$DOWNLOAD_DIR/rmvpe_20231006.onnx" ]; then
    cp "$DOWNLOAD_DIR/rmvpe_20231006.onnx" "$VCCLIENT_DIR/modules/rmvpe/"
    echo "✓ rmvpe_20231006.onnx -> modules/rmvpe/"
else
    echo "✗ rmvpe_20231006.onnx 不存在，跳过"
fi

# 2. rinna_hubert
if [ -f "$DOWNLOAD_DIR/rinna_hubert_base-f.onnx" ]; then
    cp "$DOWNLOAD_DIR/rinna_hubert_base-f.onnx" "$VCCLIENT_DIR/modules/rinna_hubert/"
    echo "✓ rinna_hubert_base-f.onnx -> modules/rinna_hubert/"
else
    echo "✗ rinna_hubert_base-f.onnx 不存在，跳过"
fi

# 3. fcpe
if [ -f "$DOWNLOAD_DIR/fcpe.onnx" ]; then
    cp "$DOWNLOAD_DIR/fcpe.onnx" "$VCCLIENT_DIR/modules/fcpe/"
    echo "✓ fcpe.onnx -> modules/fcpe/"
else
    echo "✗ fcpe.onnx 不存在，跳过"
fi

# 4. contentvec
if [ -f "$DOWNLOAD_DIR/contentvec-f.onnx" ]; then
    cp "$DOWNLOAD_DIR/contentvec-f.onnx" "$VCCLIENT_DIR/modules/contentvec/"
    echo "✓ contentvec-f.onnx -> modules/contentvec/"
else
    echo "✗ contentvec-f.onnx 不存在，跳过"
fi

# 5. tsukuyomi 模型
if [ -f "$DOWNLOAD_DIR/tsukuyomi_v2_40k_e100_float.onnx" ]; then
    cp "$DOWNLOAD_DIR/tsukuyomi_v2_40k_e100_float.onnx" "$VCCLIENT_DIR/upload_dir/"
    echo "✓ tsukuyomi_v2_40k_e100_float.onnx -> upload_dir/"
else
    echo "✗ tsukuyomi_v2_40k_e100_float.onnx 不存在，跳过"
fi

# 6. tsukuyomi 图片
if [ -f "$DOWNLOAD_DIR/tsukuyomi_chan.png" ]; then
    cp "$DOWNLOAD_DIR/tsukuyomi_chan.png" "$VCCLIENT_DIR/upload_dir/"
    echo "✓ tsukuyomi_chan.png -> upload_dir/"
else
    echo "✗ tsukuyomi_chan.png 不存在，跳过"
fi

echo ""
echo "========================================="
echo "文件复制完成！"

echo "执行清理..."
# 清理下载目录
rm -rfv "$DOWNLOAD_DIR"
echo "✓ 下载目录已清理: $DOWNLOAD_DIR"
echo "========================================="

echo "所有操作已完成！"

echo "正在打开模型下载页面..."
./模型下载ModelDownload.sh