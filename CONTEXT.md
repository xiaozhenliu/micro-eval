# micro-eval 领域语言

本文记录 micro-eval 已确认的领域术语，避免临时简称意外变成产品或架构概念。

## Language

**正常 workspace 生命周期**:
一次 RunCell 从 workspace 建立、执行、终态观察到清理和结果提交的正常过程。执行位置、
隔离等级和稳定性等级是需要分别说明的独立维度。
_Avoid_: `local-core`
