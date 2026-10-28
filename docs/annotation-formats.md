# 标注格式 / Annotation formats

批量页支持自动检测，也可手动指定格式。所有坐标最终转换为**原图像素 xyxy**，右/下开区间。

## Pascal VOC XML

- 扫描文件夹下所有 `*.xml`，读取 `<filename>`、`<size>`、`<object><bndbox>`。
- `xmax/ymax` 按 VOC 约定为**包含**边界，内部转换时 `+1`。
- `<difficult>1</difficult>` 保留为元数据。
- 空 XML（无 `<object>`）会作为“空标注/负样本”显示，默认跳过。
- 图片解析顺序：`image_root/<filename>` → XML 同级 → 同级 `JPEGImages/` → 递归索引。

示例：`Annotations/*.xml`（自行准备 VOC 标注）。

## COCO JSON

```json
{
  "images": [{"id": 1, "file_name": "a.jpg", "width": 1920, "height": 1080}],
  "annotations": [{"id": 1, "image_id": 1, "category_id": 3, "bbox": [x, y, w, h]}],
  "categories": [{"id": 3, "name": "tank"}]
}
```

- bbox `xywh` → `xyxy`。
- `score` 保留；`iscrowd` 记录为 difficult。
- 按 `file_name` + `image_root` 配对；支持图片目录中无标注的图片。

## LabelMe JSON

```json
{
  "imagePath": "a.jpg",
  "imageWidth": 1920,
  "imageHeight": 1080,
  "shapes": [
    {"label": "tank", "shape_type": "rectangle", "points": [[x1, y1], [x2, y2]]}
  ]
}
```

- rectangle 取两点外接框；polygon/其他形状取点集外接框。
- 图片相对 JSON 目录或 `image_root` 解析。

## YOLO txt

```text
0 cx cy w h
```

- 坐标为归一化 `cx cy w h`，需要图片尺寸（自动读取图片头）。
- 类别名从 `classes.txt` 或 `data.yaml` 的 `names` 读取；缺失时用 `class_0`。
- 必须提供图片文件夹（或在 labels 同级找 `JPEGImages/`、`images/`）。
- 空 txt 作为负样本。

## CSV / 通用 JSON 坐标

支持的列名：

- 图片：`image` / `filename` / `file` / `path` / `image_path`
- 坐标：`x1,y1,x2,y2` / `xmin,ymin,xmax,ymax` / `xmin_1920,ymin_1920,xmax_1920,ymax_1920` / `left,top,right,bottom`
- 标签：`class` / `label` / `category`

`xmax`/`ymax` 列会自动 `+1`；`x1/y1/x2/y2` 视为右/下开区间。`manifest.csv` 的 1920 坐标可直接使用，图片目录选 `JPEGImages`。

## 通用 JSON 行列表

```json
[
  {"filename": "a.jpg", "x1": 10, "y1": 20, "x2": 300, "y2": 400, "label": "tank"}
]
```

## 配对与错误

- 配对优先级：相对路径 → 文件名（Windows 忽略大小写）→ 递归索引。
- 同名文件冲突会使用第一个并给出警告。
- 找不到图片的记录会标记为“缺图片”，批量任务中计为失败。
- 空框/零面积框会被丢弃并记录警告。
- label 只用于过滤、命名和导出，**不参与模型推理**（模型是框内前景二分类）。
