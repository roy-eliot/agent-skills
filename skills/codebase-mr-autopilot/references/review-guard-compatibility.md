# Review Guard 兼容性

初始化期间以及每次派发 R1/R2/R3 前读取本文。`review-guard` 是必需的同级 Skill，不是可选适配器。

## 兼容包

当前 Autopilot 版本只接受以下 `review-guard` package digest：

```text
1d303873c29259b242d023f7822a78c5be9c77558a6009e4d2a5cbbcc5374d72
```

所有 digest 一律用同一个脚本计算，不得手工复现算法：

```text
scripts/package-digest.py <review-guard-package-root> --expect <compatible-digest>
```

退出码 `3` 即不匹配，stderr 会给出规范 root 和完整文件清单。

发布新的 Review Guard 版本时，必须有意识地更新 Autopilot 兼容性并生成新的双 Skill bundle。不得接受任意同名包。

## 无歧义发现

1. 枚举当前运行时及其 user/project Skill 发现根目录暴露的所有 `review-guard` 候选项。
2. 解析 symlink，并对共享同一规范真实路径的候选项去重；如果支持，还要比较文件系统身份。
3. 必须恰好存在一个不同的规范 package root。
4. 验证 `SKILL.md` frontmatter 中的 name 为 `review-guard`，并用上述脚本确认 package digest 位于兼容列表中。
5. 确认全新的直接子级评审步骤能够自主调用该精确候选项，而无需继续委派。Autopilot 内部同名嵌套目录不属于可发现的同级 Skill。

候选项为零、存在多个不同候选项、digest 不兼容或 deny rule 阻止调用时，返回终止状态 `blocked_review_dependency`。绝不能选择搜索路径中第一个匹配项。

## 每轮证明

digest 检查不只发生在初始化阶段：

1. 主控派发评审步骤前，紧邻的上一个直接步骤把规范 package digest 记录到评审请求产物中；主控只传递产物路径。
2. 直接评审步骤加载 `SKILL.md` 和该轮所需全部引用资源后运行脚本，并记录 `review_skill_digest_before`。
3. 评审步骤返回前立即再次检查，并记录 `review_skill_digest_after`。
4. 主控只验证紧凑信封和产物路径边界。接收结果的直接修改步骤加载证明，并在应用任何问题前重新计算 `review_skill_digest_received`；`commit_reply` 在提交前和推送前门禁再次检查。
5. 每个观测到的 digest 都必须等于不可变范围中的 digest，且彼此相等。

任何不匹配都返回 `blocked_review_dependency`；按常规阻塞规则隔离本轮持有的未提交变更。不得使用跨依赖变化生成的问题。

该机制用于发现实时评审期间的常规包更新或替换。故意在每次证明之间替换完整包、再恢复完全相同字节的进程，不属于可信本地用户威胁模型的覆盖范围。
