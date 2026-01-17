"""
影像识别路由
"""
from io import BytesIO
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import Response
from PIL import Image

router = APIRouter(prefix="/recognize_image", tags=["Image Recognition"])


@router.post("/", summary="影像识别：将图片转为灰度图")
async def recognize_image(file: UploadFile = File(...)):
    """
    接收一个图片文件，并将其转换为灰度图。
    这是一个简单的示例，您可以替换为更复杂的影像识别逻辑。
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="上传文件必须是图片格式")

    try:
        # 读取图片文件内容
        image_bytes = await file.read()
        image = Image.open(BytesIO(image_bytes))

        # 这里可以替换为你的影像识别模型
        # 示例：将图片转换为灰度图
        grayscale_image = image.convert("L")

        # 将灰度图转换为 bytes
        img_byte_arr = BytesIO()
        grayscale_image.save(img_byte_arr, format="PNG")
        img_byte_arr = img_byte_arr.getvalue()

        # 返回灰度图
        return Response(content=img_byte_arr, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"影像处理失败: {str(e)}")
