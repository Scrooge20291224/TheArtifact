cmake_minimum_required(VERSION 3.15)
project(proxy_sdl2 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

# 先备份原始 SDL2.dll → SDL2_orig.dll，然后我们生成的 SDL2.dll 是 proxy
# 编译前手动做这步，或者用 install 步骤做

add_library(proxy_sdl2 SHARED
    src/proxy_sdl2.cpp
)

# 关键：proxy.def 里写了所有 812 个转发导出 + 我们自定义的 hook
target_sources(proxy_sdl2 PRIVATE src/proxy.def)

# .def 文件要让 linker 当 linker flag 读
# 但 proxy.def 里的格式是 "Function = SDL2_orig.Function"，这会让 linker 做转发
# 不过我们自己定义的 SDL_Init / SDL_PollEvent 已经在 proxy_sdl2.cpp 里实现了
# 所以 proxy.def 里的同名转发会被我们的实现覆盖（我们先定义，.def 里的转发冲突被忽略）
# 等一下——实际上 .def 里的转发会生成同名导出，和我们的 __declspec(dllexport) 冲突
# 解法：proxy.def 里去掉 SDL_Init 和 SDL_PollEvent 这两个，只转发其他 810 个
# 先把 proxy.def 里这俩删除，我们自己实现

set_target_properties(proxy_sdl2 PROPERTIES
    OUTPUT_NAME "SDL2"
    PREFIX ""
    SUFFIX ".dll"
)

# 我们要在 proxy_sdl2.cpp 里的 GetProcAddress 调用 SDL2_orig.dll 的函数
# 所以必须延迟加载，不然 LINK 阶段会去解析 SDL2_orig.dll 的导入
target_link_libraries(proxy_sdl2 PRIVATE
    delayimp
)
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} /DELAYLOAD:SDL2_orig.dll")

# install：编译后把 proxy SDL2.dll 输出到单独目录
install(TARGETS proxy_sdl2 DESTINATION proxy_output)

# 备份脚本提示
message(STATUS "============================================")
message(STATUS "编译后部署步骤：")
message(STATUS "  1. 把游戏目录的 SDL2.dll 改名为 SDL2_orig.dll")
message(STATUS "  2. 把编译产物 SDL2.dll 复制到游戏目录")
message(STATUS "  3. 启动游戏，检查 proxy_sdl2.log")
message(STATUS "============================================")
