single_port_ram = """module SinglePortRam #
(
  parameter DATA_WIDTH = 8,
  parameter ADDR_WIDTH = 4,
  parameter RAM_DEPTH = 1 << ADDR_WIDTH
)
(
  input clk,
  input rst,
  input [ADDR_WIDTH-1:0] ram_addr,
  input [DATA_WIDTH-1:0] ram_d,
  input ram_we,
  output [DATA_WIDTH-1:0] ram_q
);

  reg [DATA_WIDTH-1:0] mem [0:RAM_DEPTH-1];
  reg [ADDR_WIDTH-1:0] read_addr;

  assign ram_q = mem[read_addr];
  always @ (posedge clk) begin
    if (ram_we)
      mem[ram_addr] <= ram_d;
  read_addr <= ram_addr;
  end
endmodule
"""

bidirectional_single_port_ram = """module BidirectionalSinglePortRam #
(
  parameter DATA_WIDTH = 8,
  parameter ADDR_WIDTH = 4,
  parameter RAM_LENGTH = 16,
  parameter RAM_DEPTH = 1 << (ADDR_WIDTH-1)
)
(
  input clk,
  input rst,
  input [ADDR_WIDTH-1:0] ram_addr,
  input [DATA_WIDTH-1:0] ram_d,
  input ram_we,
  output [DATA_WIDTH-1:0] ram_q,
  output [ADDR_WIDTH-1:0] ram_len
);
  reg [DATA_WIDTH-1:0] mem [0:RAM_DEPTH-1];
  reg [ADDR_WIDTH-1:0] read_addr;

  /*
  integer i;
  initial begin
    for (i = 0; i < RAM_DEPTH; i = i + 1)
      mem[i] = 0;
  end
  */
  function [ADDR_WIDTH-1:0] address (
    input [ADDR_WIDTH-1:0] in_addr
  );
  begin
    if (in_addr[ADDR_WIDTH-1] == 1'b1) begin
      address = RAM_LENGTH + in_addr;
  end else begin
      address = in_addr;
    end
  end
  endfunction // address
  wire [ADDR_WIDTH-1:0] a;
  assign a = address(ram_addr);
  assign ram_q = mem[read_addr];
  assign ram_len = RAM_LENGTH;
  always @ (posedge clk) begin
    if (ram_we)
      mem[ram_addr] <= ram_d;
  read_addr <= a;
  end
endmodule
"""

fifo = """module FIFO #
(
 parameter integer DATA_WIDTH = 32,
 parameter integer ADDR_WIDTH = 2,
 parameter integer LENGTH = 4
)
(
  input clk,
  input rst,
  input [DATA_WIDTH - 1 : 0]  din,
  input write,
  output full,
  output [DATA_WIDTH - 1 : 0] dout,
  input read,
  output empty,
  output will_full,
  output will_empty
);

reg [ADDR_WIDTH - 1 : 0] head;
reg [ADDR_WIDTH - 1 : 0] tail;
reg [ADDR_WIDTH : 0] count;
wire we;
assign we = write && !full;

reg [DATA_WIDTH - 1 : 0] mem [0 : LENGTH - 1];
initial begin : initialize_mem
  integer i;
  for (i = 0; i < LENGTH; i = i + 1) begin
      mem[i] = 0;
  end
end

always @(posedge clk) begin
  if (we) mem[head] <= din;
end
assign dout = mem[tail];

assign full = count >= LENGTH;
assign empty = count == 0;
assign will_full = write && !read && count == LENGTH-1;
assign will_empty = read && !write && count == 1;

always @(posedge clk) begin
  if (rst == 1) begin
    head <= 0;
    tail <= 0;
    count <= 0;
  end else begin
    if (write && read) begin
      if (count == LENGTH) begin
        count <= count - 1;
        tail <= (tail == (LENGTH - 1)) ? 0 : tail + 1;
      end else if (count == 0) begin
        count <= count + 1;
        head <= (head == (LENGTH - 1)) ? 0 : head + 1;
      end else begin
        count <= count;
        head <= (head == (LENGTH - 1)) ? 0 : head + 1;
        tail <= (tail == (LENGTH - 1)) ? 0 : tail + 1;
      end
    end else if (write) begin
      if (count < LENGTH) begin
        count <= count + 1;
        head <= (head == (LENGTH - 1)) ? 0 : head + 1;
      end
    end else if (read) begin
      if (count > 0) begin
        count <= count - 1;
        tail <= (tail == (LENGTH - 1)) ? 0 : tail + 1;
      end
    end
  end
end
endmodule
"""
