SubSentry Foxmail MAPI注册路径修复工具
=====================================

适用范围
--------
仅适用于已经确认以下两个条件的值班机：

1. 注册表仍指向：
   D:\Program Files\Foxmail 7.2\7.2.25.542\FMMAPI32.dll
2. 当前实际文件位于：
   D:\Program Files\Foxmail 7.2\7.2.25.563\FMMAPI32.dll

工具只修正Foxmail的DLLPath，不安装软件、不复制或删除Foxmail文件，
也不读取邮箱账号、密码、邮件或SubSentry业务数据。

修复步骤
--------
1. 完全退出Foxmail。
2. 右键 repair_foxmail_mapi.bat，选择“以管理员身份运行”。
3. 确认显示的新路径以7.2.25.563结尾，再输入Y。
4. 出现[OK]后重新打开Foxmail。
5. 再运行Foxmail MAPI兼容性测试r2。

安全与回退
----------
- 修改前会将两处原始注册项导出到registry_backup文件夹。
- 任一备份失败时不会修改注册表。
- 任一修改失败时会自动尝试恢复原始注册项。
- 如需手动回退，右键restore_foxmail_mapi.bat并以管理员身份运行。
- 不要删除registry_backup文件夹，至少保留到全部测试结束。

重要提示
--------
如果屏幕显示的安装路径与本说明不完全一致，请选择N退出，禁止继续。
该工具只解决注册路径失效问题，不保证64位程序与Foxmail MAPI接口兼容。
