args = commandArgs(T)

##转换Rmarkdown为html

library(rmarkdown)
library(knitr)
library(ggplot2)
library(DT)
library(flextable)
library(dplyr)
library(openxlsx)
library(base64enc)

rmd <- args[1]
html_output <- args[2]
odir <- args[3]
target <- args[4]

setwd(odir)

rmarkdown::render(
  input = rmd,  # 输入文件名,eg: yaozhi.target.var.Rmd
  output_format = "html_document", # 输出格式
  output_file = html_output, # output html, yaozhi.target.CCR8.html
  output_dir = odir,    # 指定输出目录
  params = list(target = target),
  encoding = "UTF-8",               # 指定文件编码
  quiet = TRUE                      # 减少转换过程中的输出信息
)
