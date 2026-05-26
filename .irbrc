require "irb"

IRB.conf[:BACK_TRACE_LIMIT] = 100
IRB.conf[:SAVE_HISTORY] = 100000
IRB.conf[:EVAL_HISTORY] = 200
IRB.conf[:AUTO_INDENT] = true
IRB.conf[:USE_AUTOCOMPLETE] = true

# awesome_print for prettier output, when the gem is available in this context.
begin
  require "awesome_print"
  AwesomePrint.irb!
rescue LoadError
  warn "gem install awesome_print  # for prettier irb output"
end
