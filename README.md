TmpMessage is a simple plugin for Pwnagotchi that shows a long text as a scrolling message on the display.

main.plugins.tmp_message.enabled = true
main.plugins.tmp_message.file_path = "/tmp/pwnagotchi_msg.txt"
main.plugins.tmp_message.position = "bottom"
this can be change in web:
main.plugins.tmp_message.width = 16        # chars per line
main.plugins.tmp_message.lines = 3         # lines per chunk
main.plugins.tmp_message.interval = 4.0    # seconds between chunks
main.plugins.tmp_message.indent = 0        # spaces (not work correactly) 
