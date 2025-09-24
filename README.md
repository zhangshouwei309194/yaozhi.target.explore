
# 环境配置
**1 需要ubuntu操作系统，方别使用playwright进行浏览器自动化操作**
需在集群配置X11

**python3及python环境包:**
asyncio
os
dotenv
playwright
json
bs4
xlsxwriter
pandas
numpy
sys
re
glob
shutil
pathlib
argparse
argparse

**R环境包（r4.3）**
rmarkdown
knitr
ggplot2
DT
flextable
dplyr
openxlsx
base64enc

# 运行示例
## 基于靶点查询该靶点药物信息及临床试验信息的运行示例
```bash
$ python3 scriptpath/bin/yaozhi.target.query.automated.py \
	--target GRPR \
	--odir outputpath \
	--rscript Rscript
```
**上述代码会生成基于该靶点的json文件格式信息，excel信息及html报告信息**


## ADC药物查询运行示例
```bash
$ python3 scriptpath/bin/yaozhi.ADC.infocraw.py \
	--odir outputpath
```
**上述代码会生成ADC所有药物的信息**











