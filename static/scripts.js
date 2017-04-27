// Get value from index page ids
function getValue(id) {
    return parseFloat($('#' + id).text().replace('£', '').replace(',', ''))
}

// Format number as currency GBP
function gbp(value) {
    return value.toLocaleString('en-GB', {style: 'currency', currency: 'GBP'})
}

// Format number as shareprice
function shareprice(value, profitloss=false) {
    retval = value.toFixed(2)
    if (profitloss == true && value >= 0) {
        retval = '+' + retval
    }
    return retval
}

// Format number as percent with +/- and variable decimal place (default is 1)
function percent(value, precision=1) {
    var symbol = '';
    if (value >= 0) {
        symbol = '+';
    }
    return symbol + parseFloat(value).toFixed(precision) + '%'
}

// Update row colours
function updateCellColours(ident) {
    var target = $(ident + 'target-edit').val();
    var stoploss = $(ident + 'stoploss-edit').val();
    var sharegain = parseFloat($(ident + 'sharegain').text());
    var percentage = parseFloat($(ident + 'percentage p:first-child').text());
    var bid = $(ident + 'bid').text();
    
    if (bid <= parseFloat(stoploss)) {
        $(ident + 'stoploss').addClass('danger');
    } else {
        $(ident + 'stoploss').removeClass('danger');
    };
    
    if (bid >= parseFloat(target)) {
        $(ident + 'target').addClass('success');
    } else {
        $(ident + 'target').removeClass('success');
    };
    
    if (sharegain >= 0) {
        $(ident + 'sharegain').removeClass('loss');
        $(ident + 'sharegain').addClass('profit');
    } else {
        $(ident + 'sharegain').removeClass('profit');
        $(ident + 'sharegain').addClass('loss');
    };
    
    if (percentage >= 0) {
        $(ident + 'percentage').removeClass('danger');
        $(ident + 'profitloss').removeClass('danger');
    } else {
        $(ident + 'percentage').addClass('danger');
        $(ident + 'profitloss').addClass('danger');
    };
}

// Get bid price and update cell in table
function updateRow(company) {

    // Update row
    var ident = '#' + company['id'] + '-' + company['epic'] + '-'
    
    var profitperday = company['profitloss']
    if (company['daysHeld'] > 0) {
        profitperday = profitperday / company['daysHeld'];
    }
    var profitperdayelement = '<p class="perday text-right">' + gbp(profitperday) + ' /day</p>';
    
    var percentperday = company['percentage']
    if (company['daysHeld'] > 0) {
        percentperday = percentperday / company['daysHeld'];
    }
    var percentperdayelement = '<p class="perday text-right">' + percent(percentperday, 3) + ' /day</p>';
    
    $(ident + 'sharegain').text(shareprice(company['sharegain'], profitloss=true))
    $(ident + 'bid').text(shareprice(company['sellprice']));
    $(ident + 'value').text(gbp(company['value']));
    $(ident + 'profitloss').text(gbp(company['profitloss'])).append(profitperdayelement);
    $(ident + 'percentage').text(percent(company['percentage'])).append(percentperdayelement);
    
    // Update colours
    updateCellColours(ident);
}

// Update details (exposure, profit/loss etc.)
function updateTotals(company) {
    $('#exposure').text(gbp(company['exposure']));
    $('#salevalue').text(gbp(company['salevalue']));
    $('#profitloss').text(gbp(company['profitloss']));
    $('#percentage').text(percent(company['percentage']));
    
    if (company['dailyprofit'] >= 0) {
        $('#dailyprofit').addClass('profit').removeClass('loss');
        $('#dailypercent').addClass('profit').removeClass('loss');
    } else {
        $('#dailyprofit').addClass('loss').removeClass('profit');
        $('#dailypercent').addClass('loss').removeClass('profit');
    }
    $('#dailyprofit').text(gbp(company['dailyprofit']));
    $('#dailypercent').text(percent(company['dailypercent']));
    lastupdated(new Date(company['lastupdated']));
}

// Refresh onscreen data
function refreshPrices() {
	// Display last updated in local time
    var updated = Date.parse($('#lastupdated').attr('data-utc'));
    updated = new Date(updated - (new Date().getTimezoneOffset()));
    lastupdated(updated);

    // Set 'refreshPrices' button to loading...
    var $btn = $('#refreshPrices').button('loading');
    if ($btn.hasClass('btn-danger')) {
        $btn.addClass('btn-primary').removeClass('btn-danger');
    };
    $btn.addClass('btn-primary').removeClass('btn-danger');
    
    // Get latest share price data from application
    // Send each price to updateBid function
    $.getJSON('/updateshareprices').done(function(data) {
        $.each(data[0], function(key, val) {
            updateRow(val);
        })
        updateTotals(data[1]);
        
        // When done, set refresh button active and reset log button
        $btn.button('reset');
        $('#logState').button('reset').addClass('btn-primary').removeClass('btn-success');
    }).fail(function() {
        $btn.button('fail');
        
        if (!$btn.hasClass('btn-danger')) {
            $btn.addClass('btn-danger').removeClass('btn-primary');
        };
    });   
}

// Function to print extra select on statement page
function divPicker(epic) {
    if ($('#cash_category').val() == '20') {
        var $options = '';
        $.getJSON('/getepics').done(function(data) {
            $.each(data, function(key, val) {
                $options += '<option value="' + val['epic'] + '"'
                if (epic == val['epic']) {
                    $options += ' selected="selected"'
                }
                $options += '>' + val['epic'] + ' (' + val['company'] + ')</option>';
            });
            
            if ($options != '') {
                $start = '<div class="form-group" id="extraselect"><div class="col-sm-9 col-sm-push-3"><select class="form-control" name="sharedividend" id="sharedividend">';
                $end = '</select></div></div>';
                $thing = $('#cashmodal > div:nth-child(3)').after($start + $options + $end);
            }
        });
    } else {
        if ($('#extraselect')) {
            $('#extraselect').remove();
        }
    }
}

// Function to send updated data for storing when target/stop loss edited directly from index table
function updatetarget($element) {
    var ident = $element.attr('id')
    $.ajax({
        url: '/updateindex',
        type: 'POST',
        data: JSON.stringify([ident, $element.val()]),
        contentType: 'application/json; charset=utf-8',
        dataType: 'json',
        async: false,
        success: function(val) {
            var data = ident.split('-');
            updateCellColours('#' + data[0] + '-' + data[1] + '-');
        }
    });
}

// Function to print last updated on index page
function lastupdated(lastdate) {
	lastdate = lastdate.format('ddd dd mmm @ hh:MM:sstt');
    $('#lastupdated').text(lastdate);
}

$(function() {
    // Nav Bar
    // Changes portfolio when menu item selected
    $('.portfoliochange').on('click', function() {
        $.ajax({
            url: '/portfoliochange',
            type: 'POST',
            data: JSON.stringify($(this).attr('id')),
            contentType: 'application/json; charset=utf-8',
            dataType: 'json',
            async: false,
            success: function(msg) {
                if (msg == true) {
                    location.reload();
                }
            }
        });
    });
    
    // Fade out alert flashing
    setTimeout(function(){
        $('#flash').fadeOut(1000); }, 3000);

    // Index Page - Edit target/stop loss
    // Call function when focus out or enter pressed
    $('.indexform').keydown(function(e){
        if(e.keyCode == 13){
            updatetarget($(this));
        }
    }).focusout(function(){ updatetarget($(this)); });
    
    // Share Page
    // Updates company and ADVFN link when EPIC changed
    $('#epic').keyup(function() {
        $.getJSON('/getcompanyname?epic=' + $('#epic').val()).done(function(data) {
            if (data != '') {
                $('#company').text(data[0]['company']);
                $('#company').attr('value', data[0]['company']);
                $('.advfn-logo').remove();
                if ($('#company').parent().is('#advfndiv')) {
                    $('#company').unwrap();
                }
                $('#company').wrap('<div class="input-group" id="advfndiv">');
                $('#advfndiv').append('<span class="input-group-addon advfn-logo"><a href="http://uk.advfn.com/p.php?pid=financials&symbol=LSE:' + $('#epic').val().toUpperCase() + '" target="_blank"><img src="/static/images/advfn-logo.png" alt="ADVFN Logo" /></a></span>')
            } else {
                $('#company').text('');
                $('#company').attr('value', '');
                $('.advfn-logo').remove();
                if ($('#company').parent().is('#advfndiv')) {
                    $('#company').unwrap();
                }
            }
        });
    });
    
    // Share Page
    // Implement 2 datetimepickers on buydate and selldate
    var $datepickers = [$('#buydate'), $('#selldate')];
    $datepickers.forEach(function($entry) {
        $entry.datetimepicker({
            setDate: $entry.attr('value'),
            dateFormat: 'yy-mm-dd',
            timeFormat: 'HH:mm:ss',
            beforeShow: function() {
                setTimeout(function() {
                    $('.ui-datepicker').css('z-index', 99999999999999);
                }, 0);
            }
        });
    });
    
    // Share Page
    // Calculate target at 20% when button pressed
    $('#targetcalculate').click(function() {
        var targetprice = 0;
        if (parseFloat($('#buyprice').val()) > 0) {
            targetprice = parseFloat($('#buyprice').val()) * 1.2;
        }
        $('#target').focus().val(shareprice(targetprice));
    });
    
    // Share Page
    // Calculate stop loss at -10% when button pressed
    $('#stoplosscalculate').click(function() {
        var stoploss = 0;
        if (parseFloat($('#buyprice').val()) > 0) {
            stoploss = parseFloat($('#buyprice').val()) * 0.9;
        }
        $('#stoploss').focus().val(shareprice(stoploss));
    });
    
    // Share Page
    // Calculate Stamp Duty when button pressed
    $('#stampdutycalculate').click(function() {
        var stampduty = 0;
        if (parseFloat($('#buyprice').val()) > 0 && parseInt($('#quantity').val()) > 0) {
            stampduty = parseInt($('#buyprice').val()) * parseInt($('#quantity').val()) * 0.00005;
        }
        $('#stampduty').focus().val(shareprice(stampduty));
    });
    
    // Share Page
    // Calculate total buy cost when button pressed
    $('#buycostcalculate').click(function() {
        var buycost = 0;
        if (parseFloat($('#buyprice').val()) > 0 && parseInt($('#quantity').val()) > 0) {
            buycost += parseFloat($('#buyprice').val()) * 0.01 * parseInt($('#quantity').val());
        }
        if (parseFloat($('#stampduty').val()) > 0) {
            buycost += parseFloat($('#stampduty').val());
        }
        if (parseFloat($('#buytradecost').val()) > 0) {
            buycost += parseFloat($('#buytradecost').val());
        }
        if (buycost < 0) {
            buycost = 0;
        }
        $('#buycost').focus().val(shareprice(buycost));
    });
    
    // Share Page
    // Calculate total sell cost when button pressed
    $('#sellpricecalculate').click(function() {
        var sellprice = 0;
        if (parseFloat($('#sellprice').val()) > 0 && parseInt($('#quantity').val()) > 0) {
            sellprice += parseFloat($('#sellprice').val()) * 0.01 * parseInt($('#quantity').val());
        }
        if (parseFloat($('#selltradecost').val()) > 0) {
            sellprice -= parseFloat($('#selltradecost').val());
        }
        $('#value').focus().val(shareprice(sellprice));
    });
    
    // Statement Page
    // Implement datepicker
    $('#cashdatepicker').datepicker({
        dateFormat: 'yy-mm-dd'
    });
    
    // Statement Page
    $('#cash_category').on('change', divPicker);
    if ($('#cash_category').val() == 20) {
        $('#newCash').modal('show');
        divPicker($('#cash_category').attr('data-epic'));
    }
    if ($('#alertmsg').text() != '') {
        $('#newCash').modal('show');
    }
    
    // Charts Page
    // Implement 2 datetimepickers on startdate and enddate
    var $datepickers = [$('#startdate'), $('#enddate')];
    $datepickers.forEach(function($entry) {
        $entry.datepicker({
            setDate: $entry.attr('value'),
            dateFormat: 'yy-mm-dd',
            beforeShow: function() {
                setTimeout(function() {
                    $('.ui-datepicker').css('z-index', 99999999999999);
                }, 0);
            }
        });
    });
});