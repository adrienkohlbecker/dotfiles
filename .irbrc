require "irb"

IRB.conf[:BACK_TRACE_LIMIT] = 100
IRB.conf[:SAVE_HISTORY] = 100000
IRB.conf[:EVAL_HISTORY] = 200
IRB.conf[:AUTO_INDENT] = true
IRB.conf[:USE_AUTOCOMPLETE] = true

# Prettier output via amazing_print (maintained successor to awesome_print),
# falling back to awesome_print, when the gem is available in this context.
begin
  require "amazing_print"
  AmazingPrint.irb!
rescue LoadError
  begin
    require "awesome_print"
    AwesomePrint.irb!
  rescue LoadError
    warn "gem install amazing_print  # for prettier irb output"
  end
end
