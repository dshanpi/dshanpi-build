# Release locks

正式发行前在本目录增加 `<YYYY.MM.DD-N>.lock.json`。文件必须固定 ArmBianOS 和
dspi-config 的完整 commit SHA；构建脚本拒绝分支名、tag 和短 SHA。
