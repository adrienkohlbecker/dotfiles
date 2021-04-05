# Editors
#   available options: vim, mvim, mate, emacsclient...etc.
Pry.config.editor = 'vim'

class RedOutput
  def initialize(output)
    @output = output
  end

  def puts(text)
    @output.puts "\033[31m#{text}\033[0m"
  end
end

# Exception
# Pry.config.exception_handler = proc do |output, exception, instance|
#   Pry::DEFAULT_EXCEPTION_HANDLER.call(RedOutput.new(output), exception, instance)
# end

# Rails
if defined?(Rails)
  begin
    require 'rails/console/app'
    require 'rails/console/helpers'
  rescue LoadError
    require 'console_app'
    require 'console_with_helpers'
  end
end

# === Listing config ===
# Better colors - by default the headings for methods are too
# similar to method name colors leading to a "soup"
# These colors are optimized for use with Solarized scheme
# for your terminal
Pry.config.ls.heading_color = :magenta
Pry.config.ls.public_method_color = :green
Pry.config.ls.protected_method_color = :yellow
Pry.config.ls.private_method_color = :bright_black

# awesome_print gem: great syntax colorized printing
# look at ~/.aprc for more settings for awesome_print
begin
  require 'awesome_print'
  # The following line enables awesome_print for all pry output,
  # and it also enables paging
  # Pry.config.print = proc {|output, value| Pry::Helpers::BaseHelpers.stagger_output("=> #{value.ai}", output)}
  # If you want awesome_print without automatic pagination, use the line below
  Pry.config.print = proc { |output, value| output.puts value.ai }
rescue LoadError
  puts 'gem install awesome_print  # <-- highly recommended'
end

def reload
  reload!
end
