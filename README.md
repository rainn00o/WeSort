# WeSort

WeSort 是一个本地文件整理工具，当前稳定主线已经切换到仓库根目录。

## 当前状态

- 根目录就是唯一活跃主线。
- 旧版实现已经归档到 [process_archive/2026-03-24_root_stabilization_archive](/J:/GIT/WeSort/process_archive/2026-03-24_root_stabilization_archive)。
- 后续以“微调稳定”为主，不再继续做大范围推倒重写，也不再回到历史补丁覆盖模式。

## 主流程

主界面按钮顺序固定为：

1. 扫描文件
2. 重复文件处理
3. AI辅助创建分类规则
4. 执行文件分类

说明：

- 规则编辑窗口内部已经包含命中文件预览，所以主界面不再单独保留重复的“预览分类”入口。
- 扫描后可以自动检测重复，但不会自动移动重复文件；真正移动仍然需要点击“重复文件处理”。

## 当前目录结构

```text
WeSort/
|-- main.py
|-- app.py
|-- models.py
|-- paths.py
|-- config/
|-- gui/
|-- services/
|-- tests/
|-- process_archive/
`-- WeSort.spec
```

## 运行方式

推荐使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

## 配置与运行态文件

当前运行态文件全部在根目录下：

- `config/rules.json`
- `config/rules_generated.json`
- `config/api_config.json`
- `config/api_config.json.template`
- `config/ui_state.json`
- `logs/`

这些本地运行文件不应提交到仓库。

## 当前能力

- 扫描目录中的文件，并识别月份目录标签
- 检测精确重复文件，并在手动确认后移动到目标目录垃圾箱
- 生成 `重复文件清单.csv`
- 基于项目规则、特殊分类和零散文件兜底生成统一分类计划
- 在规则编辑窗口中查看命中文件预览
- 执行分类时统一处理月份前缀、重名文件和分类报告
- 使用 API 设置窗口配置模型接口并做连通性测试
- 使用 AI 生成分类规则建议，并基于当前规则继续微调

## 当前规则原则

1. 优先命中项目分类
2. 项目未命中时，再尝试特殊分类
3. 仍未命中时，归入零散文件
4. 月份目录只解析一次，后续统一复用 `month_tag`
5. 预览、执行分类、规则编辑窗口共用同一份分类计划模型

## 测试与验证

常用验证命令：

```powershell
.\.venv\Scripts\python -m py_compile main.py app.py models.py paths.py services\*.py gui\*.py tests\*.py
.\.venv\Scripts\python -m unittest discover tests
```

## 打包

当前打包配置：

- [WeSort.spec](/J:/GIT/WeSort/WeSort.spec)

打包命令：

```powershell
.\.venv\Scripts\python -m PyInstaller WeSort.spec --noconfirm
```
